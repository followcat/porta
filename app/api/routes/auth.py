from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import LoginRequest, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    user = AuthService(db).authenticate(payload.username, payload.password)
    request.session["user_id"] = user.id
    db.commit()
    return {"status": "ok", "user": UserRead.model_validate(user).model_dump()}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "ok"}
