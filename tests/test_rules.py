"""规则引擎责任链单元测试 —— 纯 Python，无需外部服务。"""

import pytest
from modules.rules_fsm.rule_engine.base import (
    ScoreCheckHandler,
    WeeklyQuotaHandler,
    BufferConflictHandler,
    build_academic_chain,
    build_sports_chain,
)


class MockRedis:
    def __init__(self, score: int):
        self._score = str(score)

    async def get(self, key):
        return self._score


# ── ScoreCheckHandler ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_check_blocks_below_threshold():
    handler = ScoreCheckHandler()
    ok, msg = await handler.handle({"user_id": "U_test", "redis": MockRedis(79)})
    assert not ok
    assert "信誉分" in msg

@pytest.mark.asyncio
async def test_score_check_blocks_zero():
    handler = ScoreCheckHandler()
    ok, msg = await handler.handle({"user_id": "U_test", "redis": MockRedis(0)})
    assert not ok

@pytest.mark.asyncio
async def test_score_check_passes_at_threshold():
    handler = ScoreCheckHandler()
    ok, _ = await handler.handle({"user_id": "U_test", "redis": MockRedis(80)})
    assert ok

@pytest.mark.asyncio
async def test_score_check_passes_full_score():
    handler = ScoreCheckHandler()
    ok, _ = await handler.handle({"user_id": "U_test", "redis": MockRedis(100)})
    assert ok

@pytest.mark.asyncio
async def test_score_check_caches_score_in_context():
    handler = ScoreCheckHandler()
    ctx = {"user_id": "U_test", "redis": MockRedis(95)}
    await handler.handle(ctx)
    assert ctx.get("_score") == 95


# ── WeeklyQuotaHandler：无时间字段时透传 ─────────────────────────────

@pytest.mark.asyncio
async def test_weekly_quota_passthrough_without_times():
    handler = WeeklyQuotaHandler()
    ctx = {"user_id": "U_test"}  # 无 start_time / end_time
    ok, _ = await handler.handle(ctx)
    assert ok  # 无时间字段 → 透传 → 无下一个节点 → True


# ── BufferConflictHandler：缺字段时透传 ──────────────────────────────

@pytest.mark.asyncio
async def test_buffer_conflict_passthrough_without_fields():
    handler = BufferConflictHandler()
    ok, _ = await handler.handle({})  # 空 ctx → 透传
    assert ok


# ── 责任链结构 ────────────────────────────────────────────────────────

def test_academic_chain_starts_with_score_check():
    chain = build_academic_chain()
    assert isinstance(chain, ScoreCheckHandler)

def test_sports_chain_starts_with_score_check():
    chain = build_sports_chain()
    assert isinstance(chain, ScoreCheckHandler)

def test_academic_chain_has_three_handlers():
    chain = build_academic_chain()
    assert chain._next is not None, "ScoreCheck 后应有下一节点"
    assert isinstance(chain._next, WeeklyQuotaHandler)
    assert chain._next._next is not None, "WeeklyQuota 后应有下一节点"
    assert isinstance(chain._next._next, BufferConflictHandler)
    assert chain._next._next._next is None, "BufferConflict 是链尾"

def test_sports_chain_has_one_handler():
    chain = build_sports_chain()
    assert chain._next is None, "体育链仅 ScoreCheck，无后续节点"


# ── 学术链端到端：信誉分不足被拦截 ──────────────────────────────────

@pytest.mark.asyncio
async def test_academic_chain_blocks_low_score():
    chain = build_academic_chain()
    ctx = {
        "user_id": "U_bad",
        "redis": MockRedis(50),
    }
    ok, msg = await chain.handle(ctx)
    assert not ok
    assert "信誉分" in msg
