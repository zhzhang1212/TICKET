from pydantic import BaseModel

class BookingRequest(BaseModel):
    user_id: str
    resource_id: str
    slot_id: str       # 例如："slot_20260418_1430" (按30分钟碎片化的时间片ID)

class BookingResponse(BaseModel):
    status: str
    message: str
    slot_id: str
