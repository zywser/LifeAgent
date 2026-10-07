from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .config import settings
from .db.base import Base
from .db.session import engine
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：建表 + 老库补字段 + 启动定时任务
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    with engine.begin() as conn:
        if "expenses" in insp.get_table_names():
            cols = [c["name"] for c in insp.get_columns("expenses")]
            if "kind" not in cols:
                conn.execute(text("ALTER TABLE expenses ADD kind VARCHAR(8) DEFAULT 'expense'"))
        if "todos" in insp.get_table_names():
            tcols = [c["name"] for c in insp.get_columns("todos")]
            if "due_at" not in tcols:
                conn.execute(text("ALTER TABLE todos ADD due_at DATETIME NULL"))
            if "reminded" not in tcols:
                conn.execute(text("ALTER TABLE todos ADD reminded INT DEFAULT 0"))
        if "users" in insp.get_table_names():
            ucols = [c["name"] for c in insp.get_columns("users")]
            if "email_notify" not in ucols:
                conn.execute(text("ALTER TABLE users ADD email_notify INT DEFAULT 1"))
            if "username" not in ucols:
                conn.execute(text("ALTER TABLE users ADD username VARCHAR(64) DEFAULT ''"))
            if "avatar" not in ucols:
                conn.execute(text("ALTER TABLE users ADD avatar VARCHAR(255) DEFAULT ''"))
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
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
