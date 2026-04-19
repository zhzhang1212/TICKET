import time
import json
import uuid
from celery import Celery
import redis
import logging

celery_app = Celery(
    "booking_worker",
    broker="redis://localhost:6379/2",
    backend="redis://localhost:6379/3"
)

sync_redis = redis.Redis.from_url("redis://localhost:6379/1", decode_responses=True)

@celery_app.task(bind=True)
def confirm_booking_task(self, user_id: str, resource_id: str, slot_id: str, voucher: str, timestamp: str):
    """
    专门的 Worker 进程。在此执行 DB 的 Insert 事务假动作。
    """
    try:
        logging.info(f"==> Worker 开始为 {user_id} 将订单落库...")
        time.sleep(2)
        
        ticket_info = {
            "event_name": resource_id,
            "slot_id": slot_id,
            "status": "抢票落库成功",
            "voucher": voucher,
            "timestamp": timestamp
        }
        sync_redis.hset(f"user_tickets:{user_id}", voucher, json.dumps(ticket_info))
        
        msg = {
            "status": "success", 
            "msg": f"落库成功（凭证：{voucher}，时间：{timestamp}）"
        }
        sync_redis.publish(f"notify_{user_id}", json.dumps(msg))
        
    except Exception as e:
        sync_redis.incr(f"slot_stock:{slot_id}")
        ticket_info = {
            "event_name": resource_id,
            "slot_id": slot_id,
            "status": "失败 (业务异常退单)",
            "voucher": voucher,
            "timestamp": timestamp
        }
        sync_redis.hset(f"user_tickets:{user_id}", voucher, json.dumps(ticket_info))
