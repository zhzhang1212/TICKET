from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routers.ws import router as ws_router
from modules.space.router import router as space_router
from modules.event.router import router as event_router

app = FastAPI(title="智约校园")

# 挂载静态文件与模板
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 注册业务路由
app.include_router(ws_router, prefix="/api/v1")
app.include_router(space_router, prefix="/api/v1")
app.include_router(event_router, prefix="/api/v1")

@app.get("/")
async def index(request: Request):
    # 返回前端骨架页面
    return templates.TemplateResponse(request=request, name="index.html")

@app.on_event("startup")
async def startup_event():
    # 初始化 Redis、DB 连接池等
    from core.redis_db import init_redis
    await init_redis()

@app.on_event("shutdown")
async def shutdown_event():
    from core.redis_db import close_redis
    await close_redis()
