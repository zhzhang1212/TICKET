import json
from core.redis_db import get_redis

async def check_user_eligibility(user_id: str) -> bool:
    """
    检查用户的信誉分，判断是否满足预约资格。
    从 Redis 极速读取用户分数，默认 100 分。低于 80 分限制抢票。
    """
    redis = await get_redis()
    score_key = f"user_profile:{user_id}:score"
    score = await redis.get(score_key)
    
    if score is None:
        # 初始化默认分数
        await redis.set(score_key, 100)
        score = 100
    else:
        score = int(score)
        
    if score < 80:
        return False
    return True

async def penalize_user(user_id: str, points: int):
    """
    违约未签到/未支付时扣除校园信用分。
    """
    redis = await get_redis()
    score_key = f"user_profile:{user_id}:score"
    
    # 保证存在基准分
    score = await redis.get(score_key)
    if score is None:
        score = 100
    else:
        score = int(score)
        
    new_score = max(0, score - points)
    await redis.set(score_key, new_score)
    print(f"[*] 用户 {user_id} 违约，已扣除 {points} 分。当前信誉分: {new_score}")
