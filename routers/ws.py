import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.redis_db import get_redis

router = APIRouter()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """【实时通信】监听各自用户的异步处理结果"""
    redis_client = await get_redis()
    token = websocket.query_params.get("token", "")
    bound_user_id = await redis_client.get(f"ws_token:{token}") if token else None
    if not token or bound_user_id != user_id:
        await websocket.close(code=1008, reason="ws 鉴权失败")
        return

    await websocket.accept()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"notify_{user_id}")
    
    try:
        while True:
            # 监听Redis发布的消息，通知前端
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                await websocket.send_text(message["data"])
            await asyncio.sleep(0.1)  # 防止死循环阻塞
    except WebSocketDisconnect:
        await pubsub.unsubscribe(f"notify_{user_id}")
