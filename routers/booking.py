from fastapi import APIRouter, HTTPException, Depends
from schemas.booking import BookingRequest, BookingResponse
from core.redis_db import get_redis
from core.scoring import check_user_eligibility
from worker.tasks import confirm_booking_task

router = APIRouter()

# Lua 脚本预扣库存示例 (防止超卖并基于Slot处理)
LUA_DECR_SCRIPT = """
local stock = tonumber(redis.call('get', KEYS[1]))
if stock and stock > 0 then
    redis.call('decr', KEYS[1])
    return 1
end
return 0
"""

@router.post("/booking", response_model=BookingResponse)
async def create_booking(request: BookingRequest):
    """
    接收抢订请求。进行风控和 Redis 预扣。
    """
    # 1. 规则预审 (风控)
    if not await check_user_eligibility(request.user_id):
        raise HTTPException(status_code=403, detail="信用分不足或在黑名单中")

    redis_client = await get_redis()
    
    # 2. Redis 预扣锁
    slot_key = f"slot_stock:{request.slot_id}"
    success = await redis_client.eval(LUA_DECR_SCRIPT, 1, slot_key)
    
    if not success:
        raise HTTPException(status_code=400, detail="该时段资源已满")

    # 3. 异步提交至 Celery / MQ
    # 发送任务进行最终落库排重，前端可转为 WebSocket 等待状态
    confirm_booking_task.delay(request.user_id, request.resource_id, request.slot_id)

    return BookingResponse(
        status="processing", 
        message="抢订中，请稍后正在处理...", 
        slot_id=request.slot_id
    )
