from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routers import booking

app = FastAPI(title="智约校园")

# 挂载静态文件与模板
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 注册业务路由
app.include_router(booking.router, prefix="/api/v1")

@app.get("/")
async def index(request: Request):
    # 返回前端骨架页面
    return templates.TemplateResponse("index.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    # 初始化 Redis、DB 连接池等
    from core.redis_db import init_redis
    await init_redis()

@app.on_event("shutdown")
async def shutdown_event():
    from core.redis_db import close_redis
    await close_redis()
