from pydantic import BaseModel
from typing import Optional, List

class EventCreate(BaseModel):
    event_name: str
    description: str
    slot_id: str
    voucher: Optional[str] = None
    capacity: int

class EventUpdate(BaseModel):
    event_name: Optional[str] = None
    description: Optional[str] = None
    capacity_delta: Optional[int] = None

class BookingRecord(BaseModel):
    user_id: str
    voucher: str
    timestamp: str

class EventDetailResponse(BaseModel):
    slot_id: str
    voucher: Optional[str] = None
    event_name: str
    description: str
    total_capacity: int
    remaining_stock: int
    successful_bookings: List[BookingRecord]

class EventTicketRequest(BaseModel):
    user_id: str
    resource_id: str
    slot_id: str
    voucher: Optional[str] = None       # 例如："slot_20260418_1430" (按30分钟碎片化的时间片ID)

class EventTicketResponse(BaseModel):
    status: str
    message: str
    slot_id: str
    voucher: Optional[str] = None
