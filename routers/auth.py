from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import secrets
import uuid
import json
from core.redis_db import get_redis

router = APIRouter(prefix="/auth", tags=["Global Auth"])

class LoginRequest(BaseModel):
    username: str
    password: str


async def _issue_ws_token(redis, user_id: str) -> str:
    token = secrets.token_urlsafe(24)
    await redis.setex(f"ws_token:{token}", 12 * 3600, user_id)
    return token

@router.post("/login", summary="用户登录与自动注册接口")
async def login_or_register(req: LoginRequest):
    """
    检查 Redis 中是否存在此用用户名。
    - 若不存在，自动创建（密码即为当前密码），并初始化其信誉分等所有信息。
    - 若存在，拦截比对密码。
    """
    redis = await get_redis()
    user_key = f"user:{req.username}"
    
    # 检查存在与否
    is_exists = await redis.exists(user_key)
    
    if is_exists:
        # 已存在：验证密码
        stored_password = await redis.hget(user_key, "password")
        if stored_password != req.password:
            raise HTTPException(status_code=401, detail="密码校验失败，该用户名已被注册或您输入了错误的密码。")
        
        user_id = await redis.hget(user_key, "user_id")
        reputation = await redis.hget(user_key, "reputation")
        ws_token = await _issue_ws_token(redis, user_id)
        return {
            "message": "登录成功！", 
            "user_id": user_id, 
            "username": req.username, 
            "reputation": int(reputation),
            "ws_token": ws_token,
        }
    else:
        # 不存在：走自动注册并初始化流程
        new_user_id = f"U_{uuid.uuid4().hex[:8]}"
        
        # 封装全部初始属性存入 Redis Hash 中
        await redis.hset(user_key, mapping={
            "user_id": new_user_id,
            "password": req.password,
            "reputation": "100",  # 默认满分100信誉分
            "booked_count": "0",  # 历史预定场次数量
            "rooms": "[]"         # 持有的房间（序列化JSON表）
        })

        ws_token = await _issue_ws_token(redis, new_user_id)
        
        return {
            "message": "未检索到该用户，已为您自动注册并登录！", 
            "user_id": new_user_id, 
            "username": req.username, 
            "reputation": 100,
            "ws_token": ws_token,
        }

@router.get("/profile/{user_id}", summary="获取用户各项预定状态")
async def get_user_profile(user_id: str):
    """
    返回用户所有的活动抢票状态以及空间预定情况
    """
    redis = await get_redis()
    
    # 抢票记录
    tickets_raw = await redis.hgetall(f"user_tickets:{user_id}")
    tickets = [json.loads(v) for v in tickets_raw.values()] if tickets_raw else []
    
    # 预定房间
    rooms_raw = await redis.hgetall(f"user_rooms:{user_id}")
    rooms = [json.loads(v) for v in rooms_raw.values()] if rooms_raw else []
    
    # 预定场馆
    venues_raw = await redis.hgetall(f"user_venues:{user_id}")
    venues = [json.loads(v) for v in venues_raw.values()] if venues_raw else []
    
    return {
        "tickets": tickets,
        "rooms": rooms,
        "venues": venues
    }
