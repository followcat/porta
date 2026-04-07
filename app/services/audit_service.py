from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.repositories.audit_repo import AuditLogRepository


class AuditService:
    def __init__(self, session: Session):
        self.repo = AuditLogRepository(session)

    def log(self, actor_user_id: int | None, action: str, target_type: str, target_id: str, detail: dict | None = None) -> AuditLog:
        return self.repo.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail=detail,
            )
        )
