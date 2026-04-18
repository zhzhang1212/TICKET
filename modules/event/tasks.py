import time
import json
from celery import Celery
import redis
import logging

# 初始化 Celery Worker
# Broker 使用 db 2, Backend 使用 db 3
celery_app = Celery(
    "booking_worker",
    broker="redis://localhost:6379/2",
    backend="redis://localhost:6379/3"
)

# 同步 redis client，跟 FastAPI 保持一致，使用 db 1 操作库存和 pubsub
sync_redis = redis.Redis.from_url("redis://localhost:6379/1", decode_responses=True)

@celery_app.task(bind=True)
def confirm_booking_task(self, user_id: str, resource_id: str, slot_id: str):
    """
    专门的 Worker 进程。在此执行 DB 的 Insert 事务假动作。
    """
    try:
        logging.info(f"==> Worker 开始为 {user_id} 将订单落库...")
        
        # ⚠️ 这里模拟数据库由于存在磁盘寻道时间、唯一索引校验导致的耗时 (2秒)
        time.sleep(2)
        
        # 落库成功！推送成功给 Redis PubSub 频道
        msg = {
            "status": "success", 
            "msg": f"恭喜！您已成功锁定 {slot_id} 凭证！"
        }
        sync_redis.publish(f"notify_{user_id}", json.dumps(msg))
        logging.info(f"==> Worker 落库完毕，并推送 WebSocekt 通知给 {user_id}")
        
    except Exception as e:
        logging.error(f"Booking conflict: {e}")
        # 如果因为重复键冲突，需要将 Redis 被扣的库存回退 (+1)
        sync_redis.incr(f"slot_stock:{slot_id}")
