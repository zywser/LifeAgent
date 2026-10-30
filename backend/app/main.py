from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .logging_config import setup_logging, get_logger
from .config import settings
from .auth.router import router as auth_router
from .routes.chat import router as chat_router
from .routes.notes import router as notes_router
from .routes.summary import router as summary_router
from .routes.sync import router as sync_router
from .routes.life import router as life_router
from .routes.impression import router as impression_router
from .routes.notify import router as notify_router
from .routes.conversations import router as conversations_router
from .routes.memory import router as memory_router
from .scheduler import start_scheduler, shutdown_scheduler

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：执行数据库迁移（新库建表 / 旧库 stamp / 已纳管库增量升级）+ 定时任务
    from .db.migrate import run_migrations
    from .alerting import alert
    try:
        run_migrations()
    except Exception as e:
        alert("db_migration", f"启动迁移失败：{e}")
        raise
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 请求日志：4xx 记 warning、5xx 记 error，未捕获异常记 error 后继续抛出
@app.middleware("http")
async def log_bad_requests(request, call_next):
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error("[%s] %s -> EXC %s: %s", request.method, request.url.path, type(e).__name__, e)
        raise
    if response.status_code >= 500:
        logger.error("[%s] %s -> %s", request.method, request.url.path, response.status_code)
    elif response.status_code >= 400:
        logger.warning("[%s] %s -> %s", request.method, request.url.path, response.status_code)
    return response

uploads = Path("uploads"); uploads.mkdir(exist_ok=True)
app.mount("/notes/uploads", StaticFiles(directory=str(uploads)), name="uploads")
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(notes_router)
app.include_router(summary_router)
app.include_router(sync_router)
app.include_router(life_router)
app.include_router(impression_router)
app.include_router(notify_router)
app.include_router(conversations_router)
app.include_router(memory_router)


@app.get("/health")
def health():
    return {"status": "ok"}
