from pydantic import BaseModel, field_validator, model_validator
from typing import List, Optional
from datetime import datetime, date


# ── 请求模型 ──────────────────────────────────────────────

class AcademicBookingRequest(BaseModel):
    space_id: str
    user_id: str
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time 必须晚于 start_time")
        duration_minutes = (self.end_time - self.start_time).total_seconds() / 60
        if duration_minutes < 30:
            raise ValueError("最短预约时长为 30 分钟")
        if duration_minutes > 240:
            raise ValueError("单次预约不得超过 4 小时")
        return self


class SportsBookingRequest(BaseModel):
    space_ids: List[str]   # 单场地传 1 个，组合预约传多个
    user_id: str
    slot_date: date
    slot_hour: int         # 整点小时，0-23

    @field_validator("slot_hour")
    @classmethod
    def validate_hour(cls, v):
        if not (0 <= v <= 23):
            raise ValueError("slot_hour 必须在 0-23 之间")
        return v

    @field_validator("space_ids")
    @classmethod
    def validate_space_ids(cls, v):
        if not v:
            raise ValueError("至少需要指定一个场地")
        if len(v) > 4:
            raise ValueError("组合预约最多同时锁定 4 个场地")
        return v


class CancelBookingRequest(BaseModel):
    user_id: str   # 用于核验所有权


# ── 响应模型 ──────────────────────────────────────────────

class SpaceOut(BaseModel):
    space_id: str
    name: str
    space_type: str
    capacity: int
    is_combinable: bool
    description: str

    model_config = {"from_attributes": True}


class SlotInfo(BaseModel):
    hour: int
    available: bool


class AcademicBookingOut(BaseModel):
    booking_id: str
    space_id: str
    space_name: Optional[str] = None
    actual_start: datetime
    actual_end: datetime
    status: str

    model_config = {"from_attributes": True}


class SportsBookingOut(BaseModel):
    booking_ids: List[str]
    group_booking_id: Optional[str]
    space_ids: List[str]
    slot_date: date
    slot_hour: int
    status: str


class UserBookingsOut(BaseModel):
    academic: List[AcademicBookingOut]
    sports: List[SportsBookingOut]
