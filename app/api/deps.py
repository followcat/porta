from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.db.session import get_db, get_session_factory
from app.repositories.user_repo import UserRepository


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    user = UserRepository(db).get(int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return user


def get_supervisor(request: Request):
    return request.app.state.supervisor_manager


def get_db_session_factory():
    return get_session_factory()
