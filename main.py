import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routers.ws import router as ws_router
from routers.auth import router as auth_router
from modules.space.router import router as space_router
from modules.event.router import router as event_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.redis_db import init_redis
    await init_redis()
    try:
        from core.database import init_db
        await init_db()
        await _seed_spaces()
    except Exception as e:
        logging.warning(f"[DB] PostgreSQL 未就绪，空间预订模块暂不可用：{e}")
    yield
    from core.redis_db import close_redis
    await close_redis()


app = FastAPI(title="智约校园", lifespan=lifespan)

# 挂载静态文件与模板
app.mount("/static/space", StaticFiles(directory="modules/space/static"), name="space_static")
app.mount("/static/event", StaticFiles(directory="modules/event/static"), name="event_static")
app.mount("/static/rules_fsm", StaticFiles(directory="modules/rules_fsm/static"), name="fsm_static")
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
space_templates = Jinja2Templates(directory="modules/space/templates")
event_templates = Jinja2Templates(directory="modules/event/templates")
fsm_templates = Jinja2Templates(directory="modules/rules_fsm/templates")

# 注册业务路由
app.include_router(ws_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(space_router, prefix="/api/v1")
app.include_router(event_router, prefix="/api/v1")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/space")
async def space_page(request: Request):
    return space_templates.TemplateResponse(request=request, name="index.html")

@app.get("/event")
async def event_page(request: Request):
    return event_templates.TemplateResponse(request=request, name="index.html")

@app.get("/event/detail")
async def event_detail_page(request: Request, slot_id: str = ""):
    return event_templates.TemplateResponse(request=request, name="detail.html")

@app.get("/event/ticket")
async def event_ticket_page(request: Request, order_id: str = ""):
    return event_templates.TemplateResponse(request=request, name="ticket_detail.html")

@app.get("/rules_fsm")
async def fsm_page(request: Request):
    return fsm_templates.TemplateResponse(request=request, name="index.html")


async def _seed_spaces():
    """首次启动时写入演示用的场地数据，已存在则跳过。"""
    from core.database import AsyncSessionLocal
    from core.models import Space, SpaceType
    from sqlalchemy import select

    demo_spaces = [
        Space(space_id="room_a101", name="A101 研讨室", space_type=SpaceType.academic,
              capacity=8, is_combinable=False, description="8人小型研讨室，配备投影仪"),
        Space(space_id="room_a102", name="A102 研讨室", space_type=SpaceType.academic,
              capacity=8, is_combinable=False, description="8人小型研讨室，配备白板"),
        Space(space_id="room_b201", name="B201 会议室", space_type=SpaceType.academic,
              capacity=20, is_combinable=False, description="20人中型会议室，配备视频会议系统"),
        Space(space_id="room_b202", name="B202 会议室", space_type=SpaceType.academic,
              capacity=20, is_combinable=False, description="20人中型会议室，配备投影仪"),
        Space(space_id="room_c301", name="C301 大型报告厅", space_type=SpaceType.academic,
              capacity=60, is_combinable=False, description="60人报告厅，适合讲座与答辩"),
        Space(space_id="badminton_1", name="羽毛球场 1 号", space_type=SpaceType.sports,
              capacity=4, is_combinable=True, description="标准羽毛球场"),
        Space(space_id="badminton_2", name="羽毛球场 2 号", space_type=SpaceType.sports,
              capacity=4, is_combinable=True, description="标准羽毛球场"),
        Space(space_id="badminton_3", name="羽毛球场 3 号", space_type=SpaceType.sports,
              capacity=4, is_combinable=True, description="标准羽毛球场"),
        Space(space_id="badminton_4", name="羽毛球场 4 号", space_type=SpaceType.sports,
              capacity=4, is_combinable=True, description="标准羽毛球场"),
        Space(space_id="basketball_1", name="篮球场 A 区", space_type=SpaceType.sports,
              capacity=10, is_combinable=True, description="标准篮球半场"),
        Space(space_id="basketball_2", name="篮球场 B 区", space_type=SpaceType.sports,
              capacity=10, is_combinable=True, description="标准篮球半场"),
    ]

    async with AsyncSessionLocal() as session:
        for space in demo_spaces:
            exists = await session.scalar(
                select(Space).where(Space.space_id == space.space_id)
            )
            if not exists:
                session.add(space)
        await session.commit()
