from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from modules.event.schemas import EventTicketRequest, EventCreate, EventTicketResponse, EventDetailResponse, BookingRecord, EventUpdate
from core.redis_db import get_redis
from modules.event.tasks import confirm_booking_task, payment_timeout_task
from modules.rules_fsm.fsm.order_fsm import OrderStateMachine
import json
import uuid
from datetime import datetime
from core.judge import check_seckill_prerequisites

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

    mapping = {
        "event_name": event.event_name,
        "description": event.description,
        "total_capacity": str(event.capacity),
    }
    if event.start_time:
        mapping["start_time"] = event.start_time
    if event.end_time:
        mapping["end_time"] = event.end_time
    await redis.hset(info_key, mapping=mapping)
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
        if not info:
            continue

        stock = await redis.get(slot_key)
        stock = int(stock) if stock else 0

        records = await redis.lrange(bookings_key, 0, -1)
        successful_bookings = []
        for record_str in records:
            record = json.loads(record_str)
            uid = record.get("user_id")
            oid = record.get("order_id")
            if uid and oid:
                t_str = await redis.hget(f"user_tickets:{uid}", oid)
                if t_str:
                    record["status"] = json.loads(t_str).get("status", "未知")
            successful_bookings.append(BookingRecord(**record))

        events.append(EventDetailResponse(
            slot_id=slot_id,
            event_name=info.get("event_name", ""),
            description=info.get("description", ""),
            total_capacity=int(info.get("total_capacity", 0)),
            remaining_stock=stock,
            successful_bookings=successful_bookings,
            start_time=info.get("start_time"),
            end_time=info.get("end_time")
        ))
    return events

@router.get("/{slot_id}", response_model=EventDetailResponse, summary="【用户接口】获取活动的特定信息、余票和成交记录")
async def get_event_detail(slot_id: str, user_id: Optional[str] = None):
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
        uid = record.get("user_id")
        oid = record.get("order_id")
        if uid and oid:
            t_str = await redis.hget(f"user_tickets:{uid}", oid)
            if t_str:
                record["status"] = json.loads(t_str).get("status", "未知")
        successful_bookings.append(BookingRecord(**record))

    cancel_penalty_remain_sec = 0
    if user_id:
        penalty_ttl = await redis.ttl(f"penalty:user_cancel:{user_id}:{slot_id}")
        if penalty_ttl > 0:
            cancel_penalty_remain_sec = penalty_ttl

    return EventDetailResponse(
        slot_id=slot_id,
        event_name=info.get("event_name", ""),
        description=info.get("description", ""),
        total_capacity=int(info.get("total_capacity", 0)),
        remaining_stock=stock,
        successful_bookings=successful_bookings,
        start_time=info.get("start_time"),
        end_time=info.get("end_time"),
        cancel_penalty_remain_sec=cancel_penalty_remain_sec
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
    if event.start_time is not None:
        mapping["start_time"] = event.start_time
    if event.end_time is not None:
        mapping["end_time"] = event.end_time

    if event.capacity_delta is not None and event.capacity_delta != 0:
        delta = event.capacity_delta
        current_capacity = int(info.get("total_capacity", 0))
        new_capacity = current_capacity + delta
        if new_capacity < 0:
            raise HTTPException(status_code=400, detail="有效票数不能为负")

        current_stock = await redis.get(slot_key)
        current_stock = int(current_stock) if current_stock else 0
        new_stock = max(0, current_stock + delta)

        mapping["total_capacity"] = str(new_capacity)
        await redis.set(slot_key, new_stock)

    if mapping:
        await redis.hset(info_key, mapping=mapping)
    return {"message": "更新成功"}


@router.post("/seckill", response_model=EventTicketResponse, summary="【用户接口】热门活动的门票抢注")
async def seckill_event_ticket(request: EventTicketRequest):
    redis = await get_redis()

    is_eligible, msg = await check_seckill_prerequisites(request.user_id, request.slot_id)
    if not is_eligible:
        raise HTTPException(status_code=400, detail=msg)

    slot_key = f"slot_stock:{request.slot_id}"
    order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ticket_info = {
        "event_name": request.resource_id,
        "slot_id": request.slot_id,
        "status": "待支付",
        "order_id": order_id,
        "timestamp": timestamp,
        "version": 0,
    }
    await redis.hset(f"user_tickets:{request.user_id}", order_id, json.dumps(ticket_info))

    success = await redis.eval(LUA_DECR_SCRIPT, 1, slot_key)
    if not success:
        ticket_info["status"] = "失败 (已售罄)"
        await redis.hset(f"user_tickets:{request.user_id}", order_id, json.dumps(ticket_info))
        raise HTTPException(status_code=400, detail="手慢了，该时段资源已被抢空！")

    payment_timeout_task.apply_async(
        args=[request.user_id, request.slot_id, order_id], countdown=300
    )

    return EventTicketResponse(
        status="success",
        message="抢票初步成功！请在5分钟内完成支付。",
        slot_id=request.slot_id,
        order_id=order_id,
    )


class PaymentRequest(BaseModel):
    user_id: str
    slot_id: str
    order_id: str

@router.post("/pay", summary="【用户接口】确认支付订单")
async def pay_event_ticket(request: PaymentRequest):
    redis = await get_redis()
    voucher = f"V_{uuid.uuid4().hex[:8].upper()}"

    ok, updated, reason = await OrderStateMachine.transition_async(
        redis, request.user_id, request.order_id, "pay",
        extra={"voucher": voucher},
    )
    if not ok:
        if reason == "not_found":
            raise HTTPException(status_code=404, detail="找不到该笔订单")
        if reason == "version_mismatch":
            raise HTTPException(status_code=409, detail="订单已超时关闭，请重新抢票")
        raise HTTPException(status_code=400, detail=f"当前订单状态不可支付（{reason}）")

    confirm_booking_task.delay(
        request.user_id, updated.get("event_name", ""), request.slot_id,
        request.order_id, voucher, updated.get("timestamp", ""),
    )
    return {"message": "支付成功，系统正在安排落库！", "voucher": voucher}


@router.post("/cancel", summary="【用户接口】取消订单")
async def cancel_event_ticket(request: PaymentRequest):
    redis = await get_redis()
    cancel_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ok, _, reason = await OrderStateMachine.transition_async(
        redis, request.user_id, request.order_id, "cancel",
        extra={"cancel_time": cancel_time},
    )
    if not ok:
        if reason == "not_found":
            raise HTTPException(status_code=404, detail="找不到该笔订单")
        raise HTTPException(status_code=400, detail=f"订单当前状态不可取消（{reason}）")

    await redis.incr(f"slot_stock:{request.slot_id}")
    await redis.setex(
        f"penalty:user_cancel:{request.user_id}:{request.slot_id}", 600, cancel_time
    )
    return {"message": "订单取消成功", "order_id": request.order_id}


@router.get("/ticket/{user_id}/{order_id}", summary="【用户接口】获取自己的某笔订单详情")
async def get_ticket_detail(user_id: str, order_id: str):
    redis = await get_redis()
    ticket_str = await redis.hget(f"user_tickets:{user_id}", order_id)
    if not ticket_str:
        raise HTTPException(status_code=404, detail="找不到该笔订单")
    return json.loads(ticket_str)
