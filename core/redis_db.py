import redis.asyncio as redis
import os

redis_client = None

async def init_redis():
    global redis_client
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_client = redis.from_url(f"redis://{redis_host}:6379/1", encoding="utf-8", decode_responses=True)

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()

async def get_redis():
    return redis_client
