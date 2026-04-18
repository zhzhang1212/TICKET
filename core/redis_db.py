import redis.asyncio as redis

redis_client = None

async def init_redis():
    global redis_client
    # 建立异步 Redis 连接。使用独立的 database 1 防止与旧网站的聊天功能冲突
    redis_client = redis.from_url("redis://localhost:6379/1", encoding="utf-8", decode_responses=True)

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()

async def get_redis():
    return redis_client
