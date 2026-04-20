from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime, date, timedelta
import uuid
import json

from core.database import get_db
from core.redis_db import get_redis
from core.models import Space, AcademicBooking, SportsBooking, SpaceType, BookingStatus
from modules.rules_fsm.rule_engine.base import build_academic_chain, build_sports_chain
from .schemas import (
    AcademicBookingRequest, SportsBookingRequest, CancelBookingRequest,
    SpaceOut, SlotInfo, AcademicBookingOut, SportsBookingOut, UserBookingsOut,
)

router = APIRouter(prefix="/spaces", tags=["Module A: 空间预订"])

# ── Lua：原子性多 slot 扣减，任一不可用则全部回滚 ──────────────────
LUA_MULTI_DECR = """
for i = 1, #KEYS do
    local stock = tonumber(redis.call('get', KEYS[i]))
    if stock ~= nil and stock <= 0 then
        for j = 1, i - 1 do
            redis.call('incr', KEYS[j])
        end
        return 0
    end
end
for i = 1, #KEYS do
    local stock = tonumber(redis.call('get', KEYS[i]))
    if stock == nil then
        redis.call('set', KEYS[i], 0)
    else
        redis.call('decr', KEYS[i])
    end
end
return 1
"""

SPORTS_OPEN_HOURS = list(range(8, 23))  # 08:00 - 22:00


def _sports_slot_key(space_id: str, slot_date: date, slot_hour: int) -> str:
    return f"sports_slot:{space_id}:{slot_date.isoformat()}:{slot_hour}"


async def _init_sports_slot(redis, db: AsyncSession,
                             space_id: str, slot_date: date, slot_hour: int):
    """如果 Redis 中尚无此 slot 的 key，查 DB 后按实际状态初始化。"""
    key = _sports_slot_key(space_id, slot_date, slot_hour)
    exists = await redis.exists(key)
    if exists:
        return
    booking = await db.scalar(
        select(SportsBooking).where(
            SportsBooking.space_id == space_id,
            SportsBooking.slot_date == slot_date,
            SportsBooking.slot_hour == slot_hour,
            SportsBooking.status == BookingStatus.confirmed,
        )
    )
    await redis.set(key, 0 if booking else 1)


# ── 学术空间 ──────────────────────────────────────────────────────────

@router.get("/academic", response_model=List[SpaceOut], summary="获取所有学术空间")
async def list_academic_spaces(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Space).where(Space.space_type == SpaceType.academic)
    )
    return result.scalars().all()


@router.get(
    "/academic/{space_id}/check",
    summary="查询某学术空间在指定时段是否可预约",
)
async def check_academic_availability(
    space_id: str,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")

    buffered_start = start_time - timedelta(minutes=5)
    buffered_end = end_time + timedelta(minutes=5)

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
    return {
        "available": conflict is None,
        "buffered_start": buffered_start,
        "buffered_end": buffered_end,
    }


@router.post("/academic/book", response_model=AcademicBookingOut, summary="预约学术空间")
async def book_academic_space(
    req: AcademicBookingRequest,
    db: AsyncSession = Depends(get_db),
):
    # 1. 空间存在性校验
    space = await db.scalar(
        select(Space).where(
            Space.space_id == req.space_id,
            Space.space_type == SpaceType.academic,
        )
    )
    if not space:
        raise HTTPException(status_code=404, detail="学术空间不存在")

    # 2. 责任链：信誉分 → 每周配额 → 5 分钟缓冲期冲突
    buffered_start = req.start_time - timedelta(minutes=5)
    buffered_end = req.end_time + timedelta(minutes=5)
    redis = await get_redis()

    allowed, msg = await build_academic_chain().handle({
        "user_id": req.user_id,
        "space_id": req.space_id,
        "start_time": req.start_time,
        "end_time": req.end_time,
        "buffered_start": buffered_start,
        "buffered_end": buffered_end,
        "db": db,
        "redis": redis,
    })
    if not allowed:
        raise HTTPException(status_code=403, detail=msg)

    # 3. 写入 DB（EXCLUDE 约束兜底并发竞争）
    booking_id = f"AB_{uuid.uuid4().hex[:10].upper()}"
    booking = AcademicBooking(
        booking_id=booking_id,
        space_id=req.space_id,
        user_id=req.user_id,
        actual_start=req.start_time,
        actual_end=req.end_time,
        buffered_start=buffered_start,
        buffered_end=buffered_end,
        status=BookingStatus.confirmed,
    )
    db.add(booking)
    try:
        await db.commit()
        await db.refresh(booking)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="极端并发冲突，该时段已被他人抢占，请重新选择时间")

    # 4. 同步到 Redis profile（供 /auth/profile 展示）
    record = {
        "booking_id": booking_id,
        "space_id": req.space_id,
        "space_name": space.name,
        "actual_start": req.start_time.isoformat(),
        "actual_end": req.end_time.isoformat(),
        "status": "confirmed",
    }
    await redis.hset(f"user_rooms:{req.user_id}", booking_id, json.dumps(record))

    return AcademicBookingOut(
        booking_id=booking_id,
        space_id=req.space_id,
        space_name=space.name,
        actual_start=booking.actual_start,
        actual_end=booking.actual_end,
        status="confirmed",
    )


# ── 体育设施 ──────────────────────────────────────────────────────────

@router.get("/sports", response_model=List[SpaceOut], summary="获取所有体育设施")
async def list_sports_spaces(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Space).where(Space.space_type == SpaceType.sports)
    )
    return result.scalars().all()


@router.get(
    "/sports/{space_id}/slots",
    response_model=List[SlotInfo],
    summary="查询体育设施某天各小时 Slot 可用状态",
)
async def get_sports_slots(
    space_id: str,
    slot_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    space = await db.scalar(
        select(Space).where(
            Space.space_id == space_id,
            Space.space_type == SpaceType.sports,
        )
    )
    if not space:
        raise HTTPException(status_code=404, detail="体育设施不存在")

    redis = await get_redis()
    slots: List[SlotInfo] = []

    for hour in SPORTS_OPEN_HOURS:
        await _init_sports_slot(redis, db, space_id, slot_date, hour)
        key = _sports_slot_key(space_id, slot_date, hour)
        stock = await redis.get(key)
        slots.append(SlotInfo(hour=hour, available=(int(stock) > 0)))

    return slots


@router.post("/sports/book", response_model=SportsBookingOut, summary="预约体育设施（支持组合预约）")
async def book_sports_slot(
    req: SportsBookingRequest,
    db: AsyncSession = Depends(get_db),
):
    # 1. 责任链：信誉分校验
    redis = await get_redis()
    allowed, msg = await build_sports_chain().handle({
        "user_id": req.user_id,
        "redis": redis,
    })
    if not allowed:
        raise HTTPException(status_code=403, detail=msg)

    # 2. 开放时段校验
    if req.slot_hour not in SPORTS_OPEN_HOURS:
        raise HTTPException(status_code=400, detail=f"体育设施开放时间为 {SPORTS_OPEN_HOURS[0]}:00 - {SPORTS_OPEN_HOURS[-1]}:00")

    # 3. 空间存在性 & 组合预约合法性校验
    for sid in req.space_ids:
        space = await db.scalar(
            select(Space).where(
                Space.space_id == sid,
                Space.space_type == SpaceType.sports,
            )
        )
        if not space:
            raise HTTPException(status_code=404, detail=f"体育设施 {sid} 不存在")
        if len(req.space_ids) > 1 and not space.is_combinable:
            raise HTTPException(status_code=400, detail=f"场地 {sid} 不支持组合预约")

    # 4. 初始化并原子扣减所有 slot
    for sid in req.space_ids:
        await _init_sports_slot(redis, db, sid, req.slot_date, req.slot_hour)

    slot_keys = [_sports_slot_key(sid, req.slot_date, req.slot_hour) for sid in req.space_ids]
    success = await redis.eval(LUA_MULTI_DECR, len(slot_keys), *slot_keys)
    if not success:
        raise HTTPException(status_code=409, detail="所选时段已被占用，请选择其他时间")

    # 5. 写入 DB
    group_id = f"GRP_{uuid.uuid4().hex[:8].upper()}" if len(req.space_ids) > 1 else None
    booking_ids: List[str] = []

    try:
        for sid in req.space_ids:
            bid = f"SB_{uuid.uuid4().hex[:10].upper()}"
            booking = SportsBooking(
                booking_id=bid,
                space_id=sid,
                user_id=req.user_id,
                group_booking_id=group_id,
                slot_date=req.slot_date,
                slot_hour=req.slot_hour,
                status=BookingStatus.confirmed,
            )
            db.add(booking)
            booking_ids.append(bid)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # DB 兜底触发：把 Redis 库存还回去
        for key in slot_keys:
            await redis.incr(key)
        raise HTTPException(status_code=409, detail="极端并发冲突，请重新预约")

    # 6. 同步 Redis profile
    for bid, sid in zip(booking_ids, req.space_ids):
        record = {
            "booking_id": bid,
            "space_id": sid,
            "group_booking_id": group_id,
            "slot_date": req.slot_date.isoformat(),
            "slot_hour": req.slot_hour,
            "status": "confirmed",
        }
        await redis.hset(f"user_venues:{req.user_id}", bid, json.dumps(record))

    return SportsBookingOut(
        booking_ids=booking_ids,
        group_booking_id=group_id,
        space_ids=req.space_ids,
        slot_date=req.slot_date,
        slot_hour=req.slot_hour,
        status="confirmed",
    )


# ── 取消预约（学术 & 体育通用） ──────────────────────────────────────

@router.delete("/bookings/{booking_id}", summary="取消预约")
async def cancel_booking(
    booking_id: str,
    req: CancelBookingRequest,
    db: AsyncSession = Depends(get_db),
):
    # 先查学术预约
    academic = await db.scalar(
        select(AcademicBooking).where(AcademicBooking.booking_id == booking_id)
    )
    if academic:
        if academic.user_id != req.user_id:
            raise HTTPException(status_code=403, detail="无权取消他人的预约")
        if academic.status != BookingStatus.confirmed:
            raise HTTPException(status_code=400, detail="该预约已取消或已过期")
        academic.status = BookingStatus.cancelled
        await db.commit()

        redis = await get_redis()
        await redis.hdel(f"user_rooms:{req.user_id}", booking_id)
        return {"message": "学术空间预约已取消", "booking_id": booking_id}

    # 再查体育预约
    sports = await db.scalar(
        select(SportsBooking).where(SportsBooking.booking_id == booking_id)
    )
    if sports:
        if sports.user_id != req.user_id:
            raise HTTPException(status_code=403, detail="无权取消他人的预约")
        if sports.status != BookingStatus.confirmed:
            raise HTTPException(status_code=400, detail="该预约已取消或已过期")

        # 组合预约：一起取消同 group 下所有记录
        if sports.group_booking_id:
            group_bookings = (await db.execute(
                select(SportsBooking).where(
                    SportsBooking.group_booking_id == sports.group_booking_id,
                    SportsBooking.status == BookingStatus.confirmed,
                )
            )).scalars().all()
        else:
            group_bookings = [sports]

        redis = await get_redis()
        for b in group_bookings:
            b.status = BookingStatus.cancelled
            # 归还 Redis slot 库存
            key = _sports_slot_key(b.space_id, b.slot_date, b.slot_hour)
            await redis.incr(key)
            await redis.hdel(f"user_venues:{req.user_id}", b.booking_id)

        await db.commit()
        return {
            "message": "体育场地预约已取消",
            "cancelled_booking_ids": [b.booking_id for b in group_bookings],
        }

    raise HTTPException(status_code=404, detail="预约记录不存在")


# ── 用户预约列表 ──────────────────────────────────────────────────────

@router.get("/bookings/user/{user_id}", response_model=UserBookingsOut, summary="获取用户所有预约")
async def get_user_bookings(user_id: str, db: AsyncSession = Depends(get_db)):
    academic_rows = (await db.execute(
        select(AcademicBooking, Space.name).join(
            Space, AcademicBooking.space_id == Space.space_id
        ).where(
            AcademicBooking.user_id == user_id,
            AcademicBooking.status == BookingStatus.confirmed,
        ).order_by(AcademicBooking.actual_start)
    )).all()

    academic_out = [
        AcademicBookingOut(
            booking_id=row.AcademicBooking.booking_id,
            space_id=row.AcademicBooking.space_id,
            space_name=row.name,
            actual_start=row.AcademicBooking.actual_start,
            actual_end=row.AcademicBooking.actual_end,
            status=row.AcademicBooking.status.value,
        )
        for row in academic_rows
    ]

    sports_rows = (await db.execute(
        select(SportsBooking).where(
            SportsBooking.user_id == user_id,
            SportsBooking.status == BookingStatus.confirmed,
        ).order_by(SportsBooking.slot_date, SportsBooking.slot_hour)
    )).scalars().all()

    # 按 group_booking_id 聚合
    groups: dict = {}
    for b in sports_rows:
        key = b.group_booking_id or b.booking_id
        if key not in groups:
            groups[key] = []
        groups[key].append(b)

    sports_out = [
        SportsBookingOut(
            booking_ids=[b.booking_id for b in bookings],
            group_booking_id=bookings[0].group_booking_id,
            space_ids=[b.space_id for b in bookings],
            slot_date=bookings[0].slot_date,
            slot_hour=bookings[0].slot_hour,
            status=bookings[0].status.value,
        )
        for bookings in groups.values()
    ]

    return UserBookingsOut(academic=academic_out, sports=sports_out)
