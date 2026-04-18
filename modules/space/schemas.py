from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# 模块A：多态空间专属 schemas
class SpaceBookingRequest(BaseModel):
    space_id: str
    start_time: datetime
    end_time: datetime
    # 5分钟缓冲期等将在服务端处理，无需前端传入
