from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from modules.event.schemas import EventTicketRequest, EventCreate, EventTicketResponse, EventDetailResponse, BookingRecord, EventUpdate
from core.redis_db import get_redis
from modules.event.tasks import confirm_booking_task, payment_timeout_task
import json
import uuid
from datetime import datetime
from core.scoring import check_user_eligibility

router = APIRouter(prefix="/events", tags=["Module B: 活动秒杀"])

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
    
    await redis.hset(info_key, mapping={
        "event_name": event.event_name,
        "description": event.description,
        "total_capacity": str(event.capacity),
    })
    await redis.set(slot_key, event.capacity)
    await redis.delete(f"event_bookings:{event.slot_id}")
    return {"message": f"成功发布活动 {event.slot_id}，总票数: {event.capacity}"}

@router.get("/", response_model=List[EventDetailResponse], summary="【用户/管理员接口】获取所有活动")
async def get_all_events():
    redis = await get_redis()
    cursor = b'0'
    all_keys = set()
    while cursor:
        cursor, keys = await redis.scan(cursor=cursor, match="event_info:*", count=100)
        all_keys.update(keys)
        if not cursor:
            break
            
    events = []
    for info_key in all_keys:
        if isinstance(info_key, bytes):
            info_key = info_key.decode()
        slot_id = info_key.split("event_info:")[1]
        
        slot_key = f"slot_stock:{slot_id}"
        bookings_key = f"event_bookings:{slot_id}"
        
        info = await redis.hgetall(info_key)
        if not info: continue
            
        stock = await redis.get(slot_key)
        stock = int(stock) if stock else 0
        
        records = await redis.lrange(bookings_key, 0, -1)
        successful_bookings = []
        for record_str in records:
            record = json.loads(record_str)
            successful_bookings.append(BookingRecord(**record))
            
        events.append(EventDetailResponse(
            slot_id=slot_id,
            event_name=info.get("event_name", ""),
            description=info.get("description", ""),
            total_capacity=int(info.get("total_capacity", 0)),
            remaining_stock=stock,
            successful_bookings=successful_bookings
        ))
    return events

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

@router.patch("/{slot_id}", summary="【管理员接口】更新活动信息，增减售票总数")
async def update_event(slot_id: str, event: EventUpdate):
    redis = await get_redis()
    info_key = f"event_info:{slot_id}"
    slot_key = f"slot_stock:{slot_id}"
    
    info = await redis.hgetall(info_key)
    if not info:
        raise HTTPException(status_code=404, detail="活动未发布或不存在")
        
    mapping = {}
    if event.event_name is not None:
        mapping["event_name"] = event.event_name
    if event.description is not None:
        mapping["description"] = event.description
        
    if event.capacity_delta is not None and event.capacity_delta != 0:
        delta = event.capacity_delta
        current_capacity = int(info.get("total_capacity", 0))
        new_capacity = current_capacity + delta
        if new_capacity < 0: raise HTTPException(status_code=400, detail="有效票数不能为负")
            
        current_stock = await redis.get(slot_key)
        current_stock = int(current_stock) if current_stock else 0
        new_stock = max(0, current_stock + delta)
            
        mapping["total_capacity"] = str(new_capacity)
        await redis.set(slot_key, new_stock)
        
    if mapping:
        await redis.hset(info_key, mapping=mapping)
    return {"message": "更新成功"}


class EventTicketResponse2(EventTicketResponse):
    order_id: Optional[str] = None

@router.post("/seckill", response_model=EventTicketResponse2, summary="【用户接口】热门活动的门票抢注")
async def seckill_event_ticket(request: EventTicketRequest):
    redis = await get_redis()
    
    is_eligible = await check_user_eligibility(request.user_id)
    if not is_eligible:
        raise HTTPException(status_code=403, detail="抢票失败：您的信誉分低于80分，不满足规定条件。")
        
    slot_key = f"slot_stock:{request.slot_id}"
    order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    ticket_info = {
        "event_name": request.resource_id,
        "slot_id": request.slot_id,
        "status": "待支付 (请在5分钟内完成)",
        "order_id": order_id,
        "timestamp": timestamp
    }
    await redis.hset(f"user_tickets:{request.user_id}", order_id, json.dumps(ticket_info))
    
    success = await redis.eval(LUA_DECR_SCRIPT, 1, slot_key)
    if not success:
        ticket_info["status"] = "失败 (已售罄)"
        await redis.hset(f"user_tickets:{request.user_id}", order_id, json.dumps(ticket_info))
        raise HTTPException(status_code=400, detail="手慢了，该时段资源已被抢空！")
        
    # start 5 minutes timeout task
    payment_timeout_task.apply_async(args=[request.user_id, request.slot_id, order_id], countdown=300)
    
    return EventTicketResponse2(
        status="success", 
        message=f"抢票初步成功！请在5分钟内完成支付。",
        slot_id=request.slot_id,
        order_id=order_id
    )

class PaymentRequest(BaseModel):
    user_id: str
    slot_id: str
    order_id: str

@router.post("/pay", summary="【用户接口】确认支付订单")
async def pay_event_ticket(request: PaymentRequest):
    redis = await get_redis()
    ticket_str = await redis.hget(f"user_tickets:{request.user_id}", request.order_id)
    if not ticket_str:
        raise HTTPException(status_code=404, detail="找不到该笔订单")
        
    ticket_info = json.loads(ticket_str)
    if ticket_info.get("status") != "待支付 (请在5分钟内完成)":
        raise HTTPException(status_code=400, detail=f"该订单状态为：{ticket_info.get('status')}，不可支付")
        
    voucher = f"V_{uuid.uuid4().hex[:8].upper()}"
    ticket_info["status"] = "正在入库中..."
    ticket_info["voucher"] = voucher
    await redis.hset(f"user_tickets:{request.user_id}", request.order_id, json.dumps(ticket_info))
    
    confirm_booking_task.delay(request.user_id, ticket_info.get("event_name", ""), request.slot_id, request.order_id, voucher, ticket_info["timestamp"])
    return {"message": "支付成功，系统正在安排落库！", "voucher": voucher}

@router.post("/cancel", summary="【用户接口】取消订单")
async def cancel_event_ticket(request: PaymentRequest):
    redis = await get_redis()
    ticket_str = await redis.hget(f"user_tickets:{request.user_id}", request.order_id)
    if not ticket_str:
        raise HTTPException(status_code=404, detail="找不到该笔订单")
        
    ticket_info = json.loads(ticket_str)
    old_status = ticket_info.get("status", "")
    
    if "取消" in old_status or "失败" in old_status or "已退款" in old_status or "关闭" in old_status:
        raise HTTPException(status_code=400, detail="订单当前状态不可手动取消")
        
    cancel_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ticket_info["status"] = f"已取消 (于 {cancel_time} 取消)"
    await redis.hset(f"user_tickets:{request.user_id}", request.order_id, json.dumps(ticket_info))
    
    # Increase stock back
    await redis.incr(f"slot_stock:{request.slot_id}")
    
    return {"message": "订单取消成功，未扣除信誉分。", "order_id": request.order_id}

@router.get("/ticket/{user_id}/{order_id}", summary="【用户接口】获取自己的某笔订单详情")
async def get_ticket_detail(user_id: str, order_id: str):
    redis = await get_redis()
    ticket_str = await redis.hget(f"user_tickets:{user_id}", order_id)
    if not ticket_str:
        raise HTTPException(status_code=404, detail="找不到该笔订单")
    return json.loads(ticket_str)

