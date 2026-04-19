from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routers.ws import router as ws_router
from routers.auth import router as auth_router
from modules.space.router import router as space_router
from modules.event.router import router as event_router

app = FastAPI(title="智约校园")

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
    # 返回前端骨架页面
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

@app.get("/rules_fsm")
async def fsm_page(request: Request):
    return fsm_templates.TemplateResponse(request=request, name="index.html")

@app.on_event("startup")
async def startup_event():
    # 初始化 Redis、DB 连接池等
    from core.redis_db import init_redis
    await init_redis()

@app.on_event("shutdown")
async def shutdown_event():
    from core.redis_db import close_redis
    await close_redis()
