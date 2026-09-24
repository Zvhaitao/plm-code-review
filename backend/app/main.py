"""FastAPI 入口。"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .models import Repository
from .routers import auth, repositories, reviews, settings as settings_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


async def _poll_loop(interval_minutes: int):
    """定时对所有启用的仓库执行检查。interval<=0 时不启动。"""
    from .services.worker import check_repository

    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            with SessionLocal() as db:
                repo_ids = db.scalars(select(Repository.id).where(Repository.enabled.is_(True))).all()
            for rid in repo_ids:
                # check_repository 内含网络/子进程调用,放线程池避免阻塞事件循环
                await asyncio.to_thread(check_repository, rid, trigger="scheduled")
        except Exception:  # noqa: BLE001
            logger.exception("定时检查异常")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 建表 + 初始化管理员
    from .services.worker import reset_orphaned_reviews

    reset_orphaned_reviews()  # 把上次中断遗留的 running 重置为 pending
    task = None
    if settings.poll_interval_minutes > 0:
        task = asyncio.create_task(_poll_loop(settings.poll_interval_minutes))
        logger.info("已启用定时检查,每 %s 分钟一次", settings.poll_interval_minutes)
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="PLM 自动代码评审平台", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(repositories.router)
app.include_router(reviews.router)
app.include_router(settings_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
