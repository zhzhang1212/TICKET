from fastapi import APIRouter
from .schemas import SpaceBookingRequest

# 必须声明独立命名空间，避免和活动（Event）冲突
router = APIRouter(prefix="/spaces", tags=["Module A: 空间预订"])

@router.post("/book")
async def book_space(request: SpaceBookingRequest):
    """
    负责学术空间（离散缓冲）和体育设施的预订。
    注意：此处开发者A只负责对接空间物理特性、5分钟缓冲期的合法性校验。
    """
    return {"status": "ok", "msg": "空间预约流程接入点"}
