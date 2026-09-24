"""SQLAlchemy 引擎 / 会话 / Base。"""
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

# SQLite 需要 check_same_thread=False 以支持后台任务线程
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖:请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """轻量迁移:为已存在的表补加新增列(避免升级后需删库)。仅处理简单的 ADD COLUMN。"""
    # (表名, 列名, 列定义)
    wanted = [
        ("findings", "existing_code", "TEXT DEFAULT ''"),
        ("reviews", "stage", "VARCHAR(32) DEFAULT ''"),
        ("reviews", "stage_detail", "VARCHAR(300) DEFAULT ''"),
        ("reviews", "tool_summary", "TEXT DEFAULT ''"),
    ]
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in wanted:
            if table not in existing_tables:
                continue  # 表不存在,create_all 会按新 schema 建好
            cols = {c["name"] for c in insp.get_columns(table)}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db() -> None:
    """建表 + 补列 + 初始化管理员账号。"""
    from . import models  # noqa: F401  确保模型已注册
    from .auth import ensure_admin_user

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    with SessionLocal() as db:
        ensure_admin_user(db)
