from fastapi import APIRouter, HTTPException
from .schemas import EventTicketRequest, EventCreate, EventTicketResponse, EventDetailResponse, BookingRecord
from core.redis_db import get_redis
from .tasks import confirm_booking_task
import json
import uuid
from datetime import datetime

# 必须声明独立命名空间
router = APIRouter(prefix="/events", tags=["Module B: 活动秒杀"])

# Lua 脚本预扣库存
LUA_DECR_SCRIPT = """
local stock = tonumber(redis.call('get', KEYS[1]))
if stock and stock > 0 then
    redis.call('decr', KEYS[1])
    return 1
end
return 0
"""

@router.post("/", summary="【管理员接口】发布一个可抢的时段/活动")
async def create_event(event: EventCreate):
    redis = await get_redis()
    slot_key = f"slot_stock:{event.slot_id}"
    info_key = f"event_info:{event.slot_id}"
    
    # 初始化活动元数据与库存
    await redis.hset(info_key, mapping={
        "event_name": event.event_name,
        "description": event.description,
        "total_capacity": str(event.capacity),
    })
    await redis.set(slot_key, event.capacity)
    # 清空之前的抢票记录（方便重复测试发布新活动）
    await redis.delete(f"event_bookings:{event.slot_id}")
    
    return {"message": f"成功发布活动 {event.slot_id}，总票数: {event.capacity}"}

@router.get("/{slot_id}", response_model=EventDetailResponse, summary="【用户接口】获取活动的特定信息、余票和成交记录")
async def get_event_detail(slot_id: str):
    redis = await get_redis()
    info_key = f"event_info:{slot_id}"
    slot_key = f"slot_stock:{slot_id}"
    bookings_key = f"event_bookings:{slot_id}"
    
    info = await redis.hgetall(info_key)
    if not info:
        raise HTTPException(status_code=404, detail="活动未发布或不存在")
        
    stock = await redis.get(slot_key)
    stock = int(stock) if stock else 0
    
    records = await redis.lrange(bookings_key, 0, -1)
    successful_bookings = []
    for record_str in records:
        record = json.loads(record_str)
        successful_bookings.append(BookingRecord(**record))
        
    return EventDetailResponse(
        slot_id=slot_id,
        event_name=info.get("event_name", ""),
        description=info.get("description", ""),
        total_capacity=int(info.get("total_capacity", 0)),
        remaining_stock=stock,
        successful_bookings=successful_bookings
    )

@router.post("/seckill", response_model=EventTicketResponse, summary="【用户接口】热门活动的门票抢注")
async def seckill_event_ticket(request: EventTicketRequest):
    """
    负责热门活动的门票抢注。
    """
    redis = await get_redis()
    slot_key = f"slot_stock:{request.slot_id}"
    
    # 统一使用一个凭证号作为记录ID
    voucher = f"V_{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 极速建立等待状态到用户凭证队列
    ticket_info = {
        "event_name": request.resource_id,
        "slot_id": request.slot_id,
        "status": "排队等待中...",
        "voucher": voucher,
        "timestamp": timestamp
    }
    await redis.hset(f"user_tickets:{request.user_id}", voucher, json.dumps(ticket_info))
    
    # 极速预扣
    success = await redis.eval(LUA_DECR_SCRIPT, 1, slot_key)
    if not success:
        # 秒杀失败，立刻把状态置为已失败
        ticket_info["status"] = "失败 (已售罄)"
        await redis.hset(f"user_tickets:{request.user_id}", voucher, json.dumps(ticket_info))
        raise HTTPException(status_code=400, detail="手慢了，该时段资源已被抢空！")
    
    # 极速抢占成功！修改状态
    ticket_info["status"] = "抢票成功"
    await redis.hset(f"user_tickets:{request.user_id}", voucher, json.dumps(ticket_info))

    # 异步推入队列做假装落库的耗时操作 (仅传voucher作为唯一凭证)
    confirm_booking_task.delay(request.user_id, request.resource_id, request.slot_id, voucher, timestamp)
    
    return EventTicketResponse(
        status="success", 
        message=f"秒杀队列已记录！凭证：{voucher} ({timestamp})。请留意档案中心的最终落库状态。",
        slot_id=request.slot_id
    )
