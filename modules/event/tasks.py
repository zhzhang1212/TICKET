import time
import json
import logging
import os
from celery import Celery
import redis
from modules.rules_fsm.fsm.order_fsm import OrderStateMachine

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

celery_app = Celery(
    "booking_worker",
    broker=f"redis://{REDIS_HOST}:6379/2",
    backend=f"redis://{REDIS_HOST}:6379/3"
)

sync_redis = redis.Redis.from_url(f"redis://{REDIS_HOST}:6379/1", decode_responses=True)


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
