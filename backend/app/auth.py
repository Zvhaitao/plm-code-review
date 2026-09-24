"""认证:登录、会话 Token、管理员初始化。

MVP 采用内存中的不透明会话 Token(进程内 dict)。重启后失效属预期行为;
如需持久化会话可后续换成 DB 表或 Redis,接口保持不变。
"""
import secrets

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

# token -> username
_active_sessions: dict[str, str] = {}


def _encode(password: str) -> bytes:
    # bcrypt 最多处理 72 字节,超出部分会被忽略,这里显式截断避免报错
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def ensure_admin_user(db: Session) -> None:
    """首次启动时按配置创建管理员账号。"""
    settings = get_settings()
    existing = db.scalar(select(User).where(User.username == settings.admin_username))
    if existing is None:
        db.add(User(username=settings.admin_username, password_hash=hash_password(settings.admin_password)))
        db.commit()


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user and verify_password(password, user.password_hash):
        return user
    return None


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    _active_sessions[token] = username
    return token


def destroy_session(token: str) -> None:
    _active_sessions.pop(token, None)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖:校验 Bearer Token,返回当前用户。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少登录凭证")
    token = authorization.split(" ", 1)[1].strip()
    username = _active_sessions.get(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已失效,请重新登录")
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user
