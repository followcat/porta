from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.tunnel_event import TunnelEvent


class TunnelEventRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: TunnelEvent) -> TunnelEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def list_for_tunnel(self, tunnel_id: int, limit: int = 50) -> list[TunnelEvent]:
        stmt = (
            select(TunnelEvent)
            .where(TunnelEvent.tunnel_id == tunnel_id)
            .order_by(TunnelEvent.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_recent(self, limit: int = 20) -> list[TunnelEvent]:
        stmt = select(TunnelEvent).order_by(TunnelEvent.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def count_recent_errors(self, limit: int = 20) -> int:
        stmt = (
            select(TunnelEvent)
            .where(TunnelEvent.level == "error")
            .order_by(TunnelEvent.created_at.desc())
            .limit(limit)
        )
        return len(list(self.session.scalars(stmt)))
