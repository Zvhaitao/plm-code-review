"""认证路由。"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import authenticate, create_session, destroy_session, get_current_user
from ..db import get_db
from ..models import User
from ..schemas import LoginRequest, LoginResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_session(user.username)
    return LoginResponse(token=token, username=user.username)


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        destroy_session(authorization.split(" ", 1)[1].strip())
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current
