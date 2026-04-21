"""
模块 C：订单生命周期有限状态机 (FSM)

合法流转:
    待支付  --pay-->     已确认  --confirm--> 落库成功
            --cancel-->  已取消
            --timeout--> 已关闭
    已确认  --no_show--> 已爽约

防幽灵支付：每次状态流转通过 Redis Lua CAS（版本号乐观锁）原子执行。
pay 和 timeout 都需要抢占 version=N 的唯一写入权，只有先到的一方能成功，
后到的一方因 version_mismatch 被拒绝，彻底消除竞态条件。
"""

from __future__ import annotations
import json
from typing import Optional

TRANSITIONS: dict[str, dict[str, str]] = {
    "待支付": {
        "pay":     "已确认",
        "cancel":  "已取消",
        "timeout": "已关闭",
    },
    "已确认": {
        "confirm": "落库成功",
        "no_show": "已爽约",
        "error":   "落库失败",
    },
}

# 原子 CAS：检查 (version, status) 后执行状态流转，防止并发写入冲突。
# KEYS[1]: hash key (user_tickets:{user_id})
# ARGV:    order_id, expected_version, expected_state, next_state, extra_json
_LUA_CAS = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then return {0, 'not_found'} end
local t = cjson.decode(raw)
local cur_ver = t['version'] or 0
if cur_ver ~= tonumber(ARGV[2]) then return {0, 'version_mismatch'} end
if t['status'] ~= ARGV[3] then return {0, 'state_mismatch'} end
t['status'] = ARGV[4]
t['version'] = cur_ver + 1
if ARGV[5] ~= '' then
    local ext = cjson.decode(ARGV[5])
    for k, v in pairs(ext) do t[k] = v end
end
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(t))
return {1, cjson.encode(t)}
"""


class OrderStateMachine:
    """订单 FSM，提供 async（FastAPI）和 sync（Celery）两种上下文的流转方法。"""

    @staticmethod
    def next_state(current: str, event: str) -> Optional[str]:
        return TRANSITIONS.get(current, {}).get(event)

    @staticmethod
    async def transition_async(
        redis_client,
        user_id: str,
        order_id: str,
        event: str,
        extra: Optional[dict] = None,
    ) -> tuple[bool, Optional[dict], str]:
        """FastAPI async 上下文。返回 (ok, updated_ticket, reason)。"""
        ticket_str = await redis_client.hget(f"user_tickets:{user_id}", order_id)
        if not ticket_str:
            return False, None, "not_found"

        ticket = json.loads(ticket_str)
        current = ticket.get("status", "")
        next_st = OrderStateMachine.next_state(current, event)
        if next_st is None:
            return False, None, f"invalid_transition: {current} --{event}-->"

        version = ticket.get("version", 0)
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else ""

        result = await redis_client.eval(
            _LUA_CAS, 1,
            f"user_tickets:{user_id}",
            order_id, str(version), current, next_st, extra_json,
        )
        if result[0]:
            return True, json.loads(result[1]), ""
        reason = result[1] if isinstance(result[1], str) else result[1].decode()
        return False, None, reason

    @staticmethod
    def transition_sync(
        redis_client,
        user_id: str,
        order_id: str,
        event: str,
        extra: Optional[dict] = None,
    ) -> tuple[bool, Optional[dict], str]:
        """Celery sync 上下文。返回 (ok, updated_ticket, reason)。"""
        ticket_str = redis_client.hget(f"user_tickets:{user_id}", order_id)
        if not ticket_str:
            return False, None, "not_found"

        ticket = json.loads(ticket_str)
        current = ticket.get("status", "")
        next_st = OrderStateMachine.next_state(current, event)
        if next_st is None:
            return False, None, f"invalid_transition: {current} --{event}-->"

        version = ticket.get("version", 0)
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else ""

        result = redis_client.eval(
            _LUA_CAS, 1,
            f"user_tickets:{user_id}",
            order_id, str(version), current, next_st, extra_json,
        )
        if result[0]:
            return True, json.loads(result[1]), ""
        reason = result[1] if isinstance(result[1], str) else result[1].decode()
        return False, None, reason
