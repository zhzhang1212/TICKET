import asyncio
import time
import json
import logging
import os
from typing import Optional
from celery import Celery
import redis
from modules.rules_fsm.fsm.order_fsm import OrderStateMachine
from core.redis_db import get_redis
from core.database import AsyncSessionLocal
from core.models import EventOrder, EventOrderStatus
from sqlalchemy import select, update

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

celery_app = Celery(
    "booking_worker",
    broker=f"redis://{REDIS_HOST}:6379/2",
    backend=f"redis://{REDIS_HOST}:6379/3"
)

sync_redis = redis.Redis.from_url(f"redis://{REDIS_HOST}:6379/1", decode_responses=True)


_LUA_ORDER_CAS = """
local exists = redis.call('EXISTS', KEYS[1])
if exists == 0 then return {0, 'not_found'} end

local cur_status = redis.call('HGET', KEYS[1], 'status')
local cur_version = tonumber(redis.call('HGET', KEYS[1], 'version') or '-1')

if cur_status ~= ARGV[1] then return {0, 'status_mismatch'} end
if cur_version ~= tonumber(ARGV[2]) then return {0, 'version_mismatch'} end

redis.call('HSET', KEYS[1], 'status', ARGV[3])
redis.call('HSET', KEYS[1], 'version', tostring(cur_version + 1))

if ARGV[4] ~= '' then redis.call('HSET', KEYS[1], 'voucher', ARGV[4]) end
if ARGV[5] ~= '' then redis.call('HSET', KEYS[1], 'cancel_time', ARGV[5]) end

return {1, 'ok'}
"""


async def create_order_record(
    order_id: str,
    user_id: str,
    slot_id: str,
    event_name: str,
    status: str,
    version: int,
    ticket_ts: str,
) -> bool:
    """创建订单记录（幂等 + 原子占位），供抢票主流程兜底。"""
    redis_client = await get_redis()
    key = f"event_order:{order_id}"

    created = await redis_client.hsetnx(key, "_created", "1")
    if not created:
        return False

    try:
        async with AsyncSessionLocal() as db:
            exists = await db.scalar(select(EventOrder.id).where(EventOrder.order_id == order_id))
            if exists:
                await redis_client.delete(key)
                return False

            db.add(
                EventOrder(
                    order_id=order_id,
                    user_id=user_id,
                    slot_id=slot_id,
                    event_name=event_name,
                    status=EventOrderStatus.pending,
                    version=version,
                    ticket_ts=ticket_ts,
                )
            )
            await db.commit()

        await redis_client.hset(
            key,
            mapping={
                "order_id": order_id,
                "user_id": user_id,
                "slot_id": slot_id,
                "event_name": event_name,
                "status": status,
                "version": str(version),
                "ticket_ts": ticket_ts,
            },
        )
        await redis_client.expire(key, 24 * 3600)
        return True
    except Exception:
        await redis_client.delete(key)
        raise


async def cas_transition_order(
    order_id: str,
    expected_status: str,
    expected_version: int,
    next_status: str,
    voucher: Optional[str] = None,
    cancel_time: Optional[str] = None,
) -> tuple[bool, str]:
    """订单状态 CAS（乐观锁），防止支付/取消/超时竞态写穿。"""
    redis_client = await get_redis()
    key = f"event_order:{order_id}"

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(EventOrder)
            .where(
                EventOrder.order_id == order_id,
                EventOrder.status == expected_status,
                EventOrder.version == expected_version,
            )
            .values(
                status=next_status,
                version=EventOrder.version + 1,
                voucher=voucher if voucher is not None else EventOrder.voucher,
                cancel_time=cancel_time if cancel_time is not None else EventOrder.cancel_time,
            )
        )
        await db.commit()

        if result.rowcount != 1:
            current = await db.scalar(select(EventOrder).where(EventOrder.order_id == order_id))
            if not current:
                return False, "not_found"
            if current.status != expected_status:
                return False, "status_mismatch"
            return False, "version_mismatch"

    result = await redis_client.eval(
        _LUA_ORDER_CAS,
        1,
        key,
        expected_status,
        str(expected_version),
        next_status,
        voucher or "",
        cancel_time or "",
    )

    ok = bool(result and int(result[0]) == 1)
    reason = result[1] if result and len(result) > 1 else "unknown"
    if isinstance(reason, bytes):
        reason = reason.decode()
    return ok, str(reason)


@celery_app.task(bind=True)
def confirm_booking_task(self, user_id: str, resource_id: str, slot_id: str, order_id: str, voucher: str, timestamp: str):
    """支付成功后异步落库。通过 FSM CAS 确保只有「已确认」状态的订单才能落库。"""
    try:
        logging.info(f"==> Worker 开始为 {user_id} 将订单落库...")
        time.sleep(2)

        ok, _, reason = OrderStateMachine.transition_sync(
            sync_redis, user_id, order_id, "confirm"
        )
        if not ok:
            logging.warning(f"落库跳过，订单 {order_id} 状态已变更: {reason}")
            sync_redis.incr(f"slot_stock:{slot_id}")
            return

        async def _mark_confirmed():
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(EventOrder)
                    .where(EventOrder.order_id == order_id)
                    .values(status=EventOrderStatus.settled, voucher=voucher)
                )
                await db.commit()

        asyncio.run(_mark_confirmed())

        booking_record = {
            "user_id": user_id,
            "order_id": order_id,
            "voucher": voucher,
            "timestamp": timestamp,
        }
        sync_redis.rpush(f"event_bookings:{slot_id}", json.dumps(booking_record))

        msg = {
            "status": "success",
            "msg": f"落库成功（凭证号：{voucher}，时间：{timestamp}）",
            "order_id": order_id,
            "voucher": voucher,
        }
        sync_redis.publish(f"notify_{user_id}", json.dumps(msg))

    except Exception as e:
        logging.error(f"Worker 异常，订单 {order_id}: {e}")
        sync_redis.incr(f"slot_stock:{slot_id}")
        OrderStateMachine.transition_sync(sync_redis, user_id, order_id, "error")

        async def _mark_failed():
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(EventOrder)
                    .where(EventOrder.order_id == order_id)
                    .values(status=EventOrderStatus.failed)
                )
                await db.commit()

        asyncio.run(_mark_failed())


@celery_app.task(bind=True)
def payment_timeout_task(self, user_id: str, slot_id: str, order_id: str):
    """
    延迟 5 分钟检查支付状态。
    利用 FSM CAS 乐观锁：若用户已支付（version 已变更），transition 失败，幽灵关单被拦截。
    """
    ok, _, reason = OrderStateMachine.transition_sync(
        sync_redis, user_id, order_id, "timeout"
    )
    if not ok:
        logging.info(f"超时任务跳过，订单 {order_id} 已完成流转: {reason}")
        return

    logging.warning(f"用户 {user_id} 超时未支付订单 {order_id}，判定违约。")

    async def _mark_closed():
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(EventOrder)
                .where(EventOrder.order_id == order_id)
                .values(status=EventOrderStatus.closed)
            )
            await db.commit()

    asyncio.run(_mark_closed())

    sync_redis.incr(f"slot_stock:{slot_id}")

    score_key = f"user_profile:{user_id}:score"
    score = sync_redis.get(score_key)
    score = int(score) if score is not None else 100
    sync_redis.set(score_key, max(0, score - 10))

    msg = {
        "status": "timeout",
        "msg": "支付超时，订单已关闭，扣除信誉分 10 分！",
        "order_id": order_id,
    }
    sync_redis.publish(f"notify_{user_id}", json.dumps(msg))
