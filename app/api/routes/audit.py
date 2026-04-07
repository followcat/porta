from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.repositories.audit_repo import AuditLogRepository
from app.schemas.event import AuditLogRead

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[AuditLogRead]:
    return [AuditLogRead.model_validate(item) for item in AuditLogRepository(db).list_recent(limit=200)]
