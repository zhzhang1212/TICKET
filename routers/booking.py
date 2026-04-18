import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from schemas.booking import BookingRequest, BookingResponse
from core.redis_db import get_redis
from worker.tasks import confirm_booking_task

router = APIRouter()

# 辅助模型
class EventCreate(BaseModel):
    slot_id: str
    capacity: int

# Lua 脚本预扣库存
LUA_DECR_SCRIPT = """
local stock = tonumber(redis.call('get', KEYS[1]))
if stock and stock > 0 then
    redis.call('decr', KEYS[1])
    return 1
end
return 0
"""

@router.post("/events")
async def create_event(event: EventCreate):
    """【管理员接口】发布一个可抢的时段/活动"""
    redis = await get_redis()
    slot_key = f"slot_stock:{event.slot_id}"
    await redis.set(slot_key, event.capacity)
    return {"message": f"成功发布活动 {event.slot_id}，总票数: {event.capacity}"}

@router.post("/booking", response_model=BookingResponse)
async def create_booking(request: BookingRequest):
    """【用户接口】抢票防重网关"""
    redis = await get_redis()
    slot_key = f"slot_stock:{request.slot_id}"
    
    # 极速预扣
    success = await redis.eval(LUA_DECR_SCRIPT, 1, slot_key)
    if not success:
        raise HTTPException(status_code=400, detail="手慢了，该时段资源已被抢空！")

    # 异步推入队列做假装落库的耗时操作
    confirm_booking_task.delay(request.user_id, request.resource_id, request.slot_id)

    return BookingResponse(
        status="processing", 
        message="抢订请求已接收，正在排队落库生成凭证...", 
        slot_id=request.slot_id
    )

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """【实时通信】监听各自用户的抢票结果"""
    await websocket.accept()
    redis_client = await get_redis()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"notify_{user_id}")
    
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                await websocket.send_text(message["data"])
            await asyncio.sleep(0.1) # 防止死循环阻塞
    except WebSocketDisconnect:
        await pubsub.unsubscribe(f"notify_{user_id}")
