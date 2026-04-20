import enum
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime,
    Date, Enum, ForeignKey, Index, event, text
)
from sqlalchemy.schema import DDL
from core.database import Base


class SpaceType(str, enum.Enum):
    academic = "academic"
    sports = "sports"


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    no_show = "no_show"


class Space(Base):
    """
    统一空间资源表，支持学术空间与体育设施两种类型。
    is_combinable 仅对 sports 类型有意义，标识该场地可被组合预约（如多场地联赛）。
    """
    __tablename__ = "spaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    space_type = Column(Enum(SpaceType), nullable=False)
    capacity = Column(Integer, nullable=False, default=1)
    is_combinable = Column(Boolean, nullable=False, default=False)
    description = Column(String, nullable=False, default="")


class AcademicBooking(Base):
    """
    学术空间预约表（会议室 / 讨论室）。
    buffered_start / buffered_end 是 actual ±5min 的系统内部锁定区间，
    对用户不可见，但 EXCLUDE 约束在此区间上做碰撞检测。
    """
    __tablename__ = "academic_bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(String, unique=True, nullable=False, index=True)
    space_id = Column(String, ForeignKey("spaces.space_id"), nullable=False)
    user_id = Column(String, nullable=False, index=True)
    actual_start = Column(DateTime(timezone=False), nullable=False)
    actual_end = Column(DateTime(timezone=False), nullable=False)
    # 系统自动计算的缓冲区间，写入时由服务层填充
    buffered_start = Column(DateTime(timezone=False), nullable=False)
    buffered_end = Column(DateTime(timezone=False), nullable=False)
    status = Column(
        Enum(BookingStatus), nullable=False, default=BookingStatus.confirmed
    )
    created_at = Column(DateTime(timezone=False), server_default=text("NOW()"))


# EXCLUDE 约束：同一 space_id 下，confirmed 状态的预约 buffered 区间不得重叠。
# 依赖 btree_gist 扩展（在 init_db 中启用）。
_academic_exclude = DDL("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'no_buffer_overlap'
            AND conrelid = 'academic_bookings'::regclass
        ) THEN
            ALTER TABLE academic_bookings
            ADD CONSTRAINT no_buffer_overlap
            EXCLUDE USING gist (
                space_id WITH =,
                tsrange(buffered_start, buffered_end, '[)') WITH &&
            )
            WHERE (status = 'confirmed');
        END IF;
    END;
    $$;
""")

event.listen(AcademicBooking.__table__, "after_create", _academic_exclude)


class SportsBooking(Base):
    """
    体育设施预约表。
    时间单位为离散小时 Slot（slot_date + slot_hour）。
    group_booking_id 非空时表示属于同一次组合预约（多场地联赛）。
    partial unique index 保证同一 slot 同一时间只有一条 confirmed 记录。
    """
    __tablename__ = "sports_bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(String, unique=True, nullable=False, index=True)
    space_id = Column(String, ForeignKey("spaces.space_id"), nullable=False)
    user_id = Column(String, nullable=False, index=True)
    # 组合预约共用同一 group_id，单场地预约为 None
    group_booking_id = Column(String, nullable=True, index=True)
    slot_date = Column(Date, nullable=False)
    slot_hour = Column(Integer, nullable=False)
    status = Column(
        Enum(BookingStatus), nullable=False, default=BookingStatus.confirmed
    )
    created_at = Column(DateTime(timezone=False), server_default=text("NOW()"))

    __table_args__ = (
        # 每个 slot 同一时间只能有一条 confirmed 预约
        Index(
            "uq_sports_slot_confirmed",
            "space_id", "slot_date", "slot_hour",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
    )
