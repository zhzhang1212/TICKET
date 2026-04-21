from pydantic import BaseModel
from typing import Optional, List

class EventCreate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    event_name: str
    description: str
    slot_id: str
    capacity: int

class EventUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    event_name: Optional[str] = None
    description: Optional[str] = None
    capacity_delta: Optional[int] = None

class BookingRecord(BaseModel):
    user_id: str
    voucher: str
    timestamp: str
    order_id: Optional[str] = None
    status: Optional[str] = "未知"

class EventDetailResponse(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    cancel_penalty_remain_sec: Optional[int] = 0
    slot_id: str
    event_name: str
    description: str
    total_capacity: int
    remaining_stock: int
    successful_bookings: List[BookingRecord]

class EventTicketRequest(BaseModel):
    user_id: str
    resource_id: str
    slot_id: str

class EventTicketResponse(BaseModel):
    status: str
    message: str
    slot_id: str
    order_id: Optional[str] = None
