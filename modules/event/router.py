from fastapi import APIRouter, HTTPException
from .schemas import EventTicketRequest, EventCreate, EventTicketResponse
from core.redis_db import get_redis
from .tasks import confirm_booking_task

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
    await redis.set(slot_key, event.capacity)
    return {"message": f"成功发布活动 {event.slot_id}，总票数: {event.capacity}"}

import json

import uuid
import json

@router.post("/seckill", response_model=EventTicketResponse, summary="【用户接口】热门活动的门票抢注")
async def seckill_event_ticket(request: EventTicketRequest):
    """
    负责热门活动的门票抢注。
    """
    redis = await get_redis()
    slot_key = f"slot_stock:{request.slot_id}"
    
    import uuid
    record_id = uuid.uuid4().hex
    
    # 极速建立等待状态到用户凭证队列
    ticket_info = {
        "event_name": request.resource_id,
        "slot_id": request.slot_id,
        "status": "排队等待中...",
        "voucher": "-"
    }
    await redis.hset(f"user_tickets:{request.user_id}", record_id, json.dumps(ticket_info))
    
    # 极速预扣
    success = await redis.eval(LUA_DECR_SCRIPT, 1, slot_key)
    if not success:
        # 秒杀失败，立刻把状态置为已失败
        ticket_info["status"] = "失败 (已售罄)"
        await redis.hset(f"user_tickets:{request.user_id}", record_id, json.dumps(ticket_info))
        raise HTTPException(status_code=400, detail="手慢了，该时段资源已被抢空！")
    
    # 极速抢占成功！立刻发放凭证并修改用户信息中的记录
    voucher = f"V_{uuid.uuid4().hex[:8].upper()}"
    ticket_info["status"] = "抢票成功"
    ticket_info["voucher"] = voucher
    await redis.hset(f"user_tickets:{request.user_id}", record_id, json.dumps(ticket_info))

    # 异步推入队列做假装落库的耗时操作 (传record_id方便更新)
    confirm_booking_task.delay(request.user_id, request.resource_id, request.slot_id, voucher, record_id)
    
    return EventTicketResponse(
        status="success", 
        message=f"秒杀队列已记录！凭证：{voucher}。请留意档案中心的最终落库状态。",
        slot_id=request.slot_id
    )
