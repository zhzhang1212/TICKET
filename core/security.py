from __future__ import annotations

import secrets

from fastapi import Cookie, HTTPException

from core.redis_db import get_redis


SESSION_COOKIE_NAME = "campus_session"
SESSION_TTL_SECONDS = 12 * 3600


async def issue_session_token(user_id: str) -> str:
    """签发服务端会话令牌，并在 Redis 中保存用户映射。"""
    redis = await get_redis()
    token = secrets.token_urlsafe(32)
    await redis.setex(f"session_token:{token}", SESSION_TTL_SECONDS, user_id)
    return token


async def get_current_user_id(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    """从 HttpOnly 会话 Cookie 解析当前登录用户。"""
    if not session_token:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    redis = await get_redis()
    user_id = await redis.get(f"session_token:{session_token}")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    return user_id