"""
模块 C：动态规则引擎（责任链模式）

职责划分：
- RuleHandler          抽象基类，持有 next 指针，未被子类拦截时自动透传
- ScoreCheckHandler    信誉分门槛：< 80 直接拦截
- WeeklyQuotaHandler   每周学术空间配额：基准 2h，信誉 80-89 减半为 1h
- BufferConflictHandler 5 分钟缓冲期重叠检测（学术空间专用）

工厂函数：
- build_academic_chain()  学术空间预约链：Score → Quota → Buffer
- build_sports_chain()    体育设施预约链：Score（Quota/Buffer 不适用体育）
"""

from __future__ import annotations
from datetime import datetime, timedelta


# ── 抽象基类 ──────────────────────────────────────────────────────────

class RuleHandler:
    """
    异步责任链节点基类。
    子类实现 _check()；未被拦截时调用 super().handle() 透传给下一节点。
    """

    def __init__(self):
        self._next: RuleHandler | None = None

    def set_next(self, handler: RuleHandler) -> RuleHandler:
        self._next = handler
        return handler

    async def handle(self, ctx: dict) -> tuple[bool, str]:
        if self._next:
            return await self._next.handle(ctx)
        return True, "通关"


# ── 具体规则处理器 ─────────────────────────────────────────────────────

class ScoreCheckHandler(RuleHandler):
    """
    规则：信誉分 < 80 → 拦截，禁止一切预约。
    context 必须包含 'user_id' 和 'redis'。
    """

    THRESHOLD = 80

    async def handle(self, ctx: dict) -> tuple[bool, str]:
        redis = ctx["redis"]
        user_id = ctx["user_id"]
        score = await redis.get(f"user_profile:{user_id}:score")
        score = int(score) if score is not None else 100

        if score < self.THRESHOLD:
            return False, f"信誉分不足（当前 {score} 分，需 ≥ {self.THRESHOLD} 分）"
        # 把分数写入 context，供下游节点复用，避免重复查询
        ctx["_score"] = score
        return await super().handle(ctx)


class WeeklyQuotaHandler(RuleHandler):
    """
    规则：学术空间每周预约上限 120 分钟；信誉分 80-89 时减半为 60 分钟。
    context 必须包含 'user_id', 'start_time', 'end_time', 'db'。
    仅在 ctx 中含有 start_time / end_time 时生效（体育场地无此字段，自动透传）。
    """

    BASE_LIMIT_MINUTES = 120
    REDUCED_SCORE_THRESHOLD = 90   # 低于此分值使用减半配额

    async def handle(self, ctx: dict) -> tuple[bool, str]:
        start_time: datetime | None = ctx.get("start_time")
        end_time: datetime | None = ctx.get("end_time")
        if not start_time or not end_time:
            return await super().handle(ctx)

        from sqlalchemy import select
        from core.models import AcademicBooking, BookingStatus

        db = ctx["db"]
        user_id = ctx["user_id"]
        score = ctx.get("_score", 100)

        limit = (
            self.BASE_LIMIT_MINUTES // 2
            if score < self.REDUCED_SCORE_THRESHOLD
            else self.BASE_LIMIT_MINUTES
        )

        # 本周一 00:00 起算
        now = datetime.now()
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)

        existing = (
            await db.execute(
                select(AcademicBooking).where(
                    AcademicBooking.user_id == user_id,
                    AcademicBooking.status == BookingStatus.confirmed,
                    AcademicBooking.actual_start >= week_start,
                    AcademicBooking.actual_start < week_end,
                )
            )
        ).scalars().all()

        used_minutes = sum(
            (b.actual_end - b.actual_start).total_seconds() / 60
            for b in existing
        )
        new_minutes = (end_time - start_time).total_seconds() / 60

        if used_minutes + new_minutes > limit:
            remaining = max(0, limit - used_minutes)
            return False, (
                f"本周学术空间已用 {int(used_minutes)} 分钟，"
                f"剩余可用 {int(remaining)} 分钟（上限 {limit} 分钟，"
                f"信誉分 {score}）"
            )

        return await super().handle(ctx)


class BufferConflictHandler(RuleHandler):
    """
    规则：学术空间 5 分钟缓冲期内有已确认预约 → 拦截。
    context 必须包含 'space_id', 'buffered_start', 'buffered_end', 'db'。
    字段缺失时自动透传（供体育场地链复用同一基类而不触发此规则）。
    """

    async def handle(self, ctx: dict) -> tuple[bool, str]:
        space_id = ctx.get("space_id")
        buffered_start = ctx.get("buffered_start")
        buffered_end = ctx.get("buffered_end")
        db = ctx.get("db")

        if not all([space_id, buffered_start, buffered_end, db]):
            return await super().handle(ctx)

        from sqlalchemy import select, and_
        from core.models import AcademicBooking, BookingStatus

        conflict = await db.scalar(
            select(AcademicBooking).where(
                and_(
                    AcademicBooking.space_id == space_id,
                    AcademicBooking.status == BookingStatus.confirmed,
                    AcademicBooking.buffered_start < buffered_end,
                    AcademicBooking.buffered_end > buffered_start,
                )
            )
        )

        if conflict:
            return False, (
                f"该时段与已有预约的缓冲期重叠，"
                f"最早可预约 {conflict.buffered_end.strftime('%H:%M')} 之后"
            )

        return await super().handle(ctx)


# ── 工厂函数 ──────────────────────────────────────────────────────────

def build_academic_chain() -> RuleHandler:
    """学术空间预约责任链：信誉分 → 每周配额 → 缓冲期冲突"""
    score = ScoreCheckHandler()
    quota = WeeklyQuotaHandler()
    buffer = BufferConflictHandler()
    score.set_next(quota).set_next(buffer)
    return score


def build_sports_chain() -> RuleHandler:
    """体育设施预约责任链：仅校验信誉分（配额与缓冲期不适用）"""
    return ScoreCheckHandler()
