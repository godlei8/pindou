from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas import LoginIn, RegisterIn, UserOut
from app.services.auth import authenticate, make_session, register

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, user_id) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name, make_session(user_id),
        max_age=s.session_max_age_days * 86400,
        httponly=True, samesite="lax", secure=False, path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_endpoint(body: RegisterIn, response: Response,
                      db: Session = Depends(get_db)) -> User:
    user = register(db, body.username, body.password, body.invite_code)
    db.commit()
    _set_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login_endpoint(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> User:
    user = authenticate(db, body.username, body.password)
    _set_cookie(response, user.id)
    return user


@router.post("/admin-login", response_model=UserOut)
def admin_login_endpoint(body: LoginIn, response: Response,
                         db: Session = Depends(get_db)) -> User:
    """管理后台自己的登录入口：只放管理员进来。密码错误照旧 401，
    密码对但不是管理员给 403——不发会话，普通账号在这里登不进去。"""
    user = authenticate(db, body.username, body.password)
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "这个账号不是管理员")
    _set_cookie(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me_endpoint(user: User = Depends(current_user)) -> User:
    return user
