import json
from core.redis_db import get_redis
from datetime import datetime

async def check_user_eligibility(user_id: str) -> bool:
    """
    检查用户的信誉分，判断是否满足预约资格。
    从 Redis 极速读取用户分数，默认 100 分。低于 80 分限制抢票。
    """
    redis = await get_redis()
    score_key = f"user_profile:{user_id}:score"
    score = await redis.get(score_key)
    
    if score is None:
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
    score = await redis.get(score_key)
    score = int(score) if score is not None else 100
    new_score = max(0, score - points)
    await redis.set(score_key, new_score)
    print(f"[*] 用户 {user_id} 违约，已扣除 {points} 分。当前信誉分: {new_score}")

async def check_seckill_prerequisites(user_id: str, slot_id: str) -> tuple[bool, str]:
    """
    统管高并发防御前线校验：
    1. 用户信誉度 (>=80)
    2. 会场活动时间 (start_time <= now <= end_time)
    3. 个人取消惩罚期 (取消后 10 分钟内不得再次预约)
    返回 (True, "OK") 或 (False, "错误原因")
    """
    redis = await get_redis()
    
    # 1. 信誉分
    is_eligible = await check_user_eligibility(user_id)
    if not is_eligible:
        return False, "您的信誉分低于80分，不满足规定条件。"
        
    # 2. 个人取消惩罚期 (10 mins)
    penalty_key = f"penalty:user_cancel:{user_id}:{slot_id}"
    penalty_ttl = await redis.ttl(penalty_key)
    if penalty_ttl > 0:
        return False, f"您刚才取消了该活动的订单，请在 {penalty_ttl} 秒后再试。"
        
    # 3. 活动时间校验
    info_key = f"event_info:{slot_id}"
    start_time_str = await redis.hget(info_key, "start_time")
    end_time_str = await redis.hget(info_key, "end_time")
    
    now = datetime.now()
    if start_time_str:
        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
            if now < start_time:
                return False, "活动预订尚未开始！"
        except ValueError:
            pass # fallback if parsing fails or formatted differently
    
    if end_time_str:
        try:
            end_time = datetime.strptime(end_time_str, "%Y-%m-%dT%H:%M:%S")
            if now > end_time:
                return False, "活动预订已经结束！"
        except ValueError:
            pass
            
    return True, "OK"
