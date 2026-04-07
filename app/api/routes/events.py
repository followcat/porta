from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.repositories.event_repo import TunnelEventRepository
from app.schemas.event import TunnelEventRead

router = APIRouter(prefix="/tunnels", tags=["events"])


@router.get("/{tunnel_id}/events", response_model=list[TunnelEventRead])
def list_tunnel_events(
    tunnel_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[TunnelEventRead]:
    return [TunnelEventRead.model_validate(item) for item in TunnelEventRepository(db).list_for_tunnel(tunnel_id, limit=100)]
