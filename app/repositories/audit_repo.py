from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, log: AuditLog) -> AuditLog:
        self.session.add(log)
        self.session.flush()
        return log

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))
