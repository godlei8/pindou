from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.services.auth import read_session


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    user_id = read_session(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    if user.is_disabled:
        # 401 而不是 403：前端收到 401 会回登录页，停用的人不该继续停在工作台
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号已停用，请联系管理员")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user
