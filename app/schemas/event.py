from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import EventLevel


class TunnelEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tunnel_id: int
    event_type: str
    level: EventLevel
    message: str
    detail: dict | None
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    action: str
    target_type: str
    target_id: str
    detail: dict | None
    created_at: datetime
