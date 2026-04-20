import time
import json
import uuid
import logging
import os
from celery import Celery
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

celery_app = Celery(
    "booking_worker",
    broker=f"redis://{REDIS_HOST}:6379/2",
    backend=f"redis://{REDIS_HOST}:6379/3"
)

sync_redis = redis.Redis.from_url(f"redis://{REDIS_HOST}:6379/1", decode_responses=True)

@celery_app.task(bind=True)
def confirm_booking_task(self, user_id: str, resource_id: str, slot_id: str, order_id: str, voucher: str, timestamp: str):
    """
    假库入库动作，用户支付成功后才调用最终落单
    """
    try:
        logging.info(f"==> Worker 开始为 {user_id} 将订单落库...")
        time.sleep(2)
        
        ticket_info = {
            "event_name": resource_id,
            "slot_id": slot_id,
            "status": "抢票落库成功",
            "order_id": order_id,
            "voucher": voucher,
            "timestamp": timestamp
        }
        sync_redis.hset(f"user_tickets:{user_id}", order_id, json.dumps(ticket_info))
        
        # 追加记录到该活动的成功列表中
        booking_record = {
            "user_id": user_id,
            "order_id": order_id,
            "voucher": voucher,
            "timestamp": timestamp
        }
        sync_redis.rpush(f"event_bookings:{slot_id}", json.dumps(booking_record))
        
        msg = {
            "status": "success", 
            "msg": f"落库成功（凭证号：{voucher}，时间：{timestamp}）",
            "order_id": order_id,
            "voucher": voucher
        }
        sync_redis.publish(f"notify_{user_id}", json.dumps(msg))
        
    except Exception as e:
        sync_redis.incr(f"slot_stock:{slot_id}")
        ticket_info = {
            "event_name": resource_id,
            "slot_id": slot_id,
            "status": "失败 (业务异常退单)",
            "order_id": order_id,
            "voucher": voucher,
            "timestamp": timestamp
        }
        sync_redis.hset(f"user_tickets:{user_id}", order_id, json.dumps(ticket_info))


@celery_app.task(bind=True)
def payment_timeout_task(self, user_id: str, slot_id: str, order_id: str):
    """
    延迟 5 分钟检查支付状态，如果仍然是待支付，则违约扣分并回滚库存
    """
    ticket_str = sync_redis.hget(f"user_tickets:{user_id}", order_id)
    if not ticket_str:
        return
        
    ticket_info = json.loads(ticket_str)
    if ticket_info.get("status") == "待支付 (请在5分钟内完成)":
        logging.warning(f"用户 {user_id} 超时未支付凭证 {order_id}，判定违约。")
        # 1. 状态改变为违约关闭
        ticket_info["status"] = "超时未支付 (已关闭)"
        sync_redis.hset(f"user_tickets:{user_id}", order_id, json.dumps(ticket_info))
        
        # 2. 库存回滚
        sync_redis.incr(f"slot_stock:{slot_id}")
        
        # 3. 扣除信誉分 10分 (通过同步或重新写redis)
        score_key = f"user_profile:{user_id}:score"
        score = sync_redis.get(score_key)
        if score is None:
            score = 100
        else:
            score = int(score)
        sync_redis.set(score_key, max(0, score - 10))
        
        # 4. 发布通知
        msg = {
            "status": "timeout", 
            "msg": "支付超时，订单已取消，已扣除信誉分 10 分！",
            "order_id": order_id
        }
        sync_redis.publish(f"notify_{user_id}", json.dumps(msg))
