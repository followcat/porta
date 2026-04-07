from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_supervisor
from app.core.enums import DesiredState
from app.db.models.user import User
from app.db.session import get_db, get_session_factory
from app.repositories.runtime_repo import TunnelRuntimeRepository
from app.schemas.tunnel import TunnelCreate, TunnelDetailRead, TunnelListFilters, TunnelRead, TunnelUpdate
from app.services.tunnel_service import TunnelService

router = APIRouter(prefix="/tunnels", tags=["tunnels"])


@router.get("", response_model=list[TunnelRead])
def list_tunnels(
    group_name: str | None = None,
    actual_state: str | None = None,
    desired_state: str | None = None,
    enabled: bool | None = Query(default=None),
    keyword: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[TunnelRead]:
    filters = TunnelListFilters(
        group_name=group_name,
        actual_state=actual_state,
        desired_state=desired_state,
        enabled=enabled,
        keyword=keyword,
    )
    return [TunnelRead.model_validate(item) for item in TunnelService(db).list_tunnels(filters)]


@router.post("", response_model=TunnelRead)
def create_tunnel(
    payload: TunnelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TunnelRead:
    tunnel = TunnelService(db).create_tunnel(payload, user.id)
    db.commit()
    db.refresh(tunnel)
    return TunnelRead.model_validate(tunnel)


@router.get("/{tunnel_id}", response_model=TunnelDetailRead)
def get_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TunnelDetailRead:
    return TunnelService(db).get_detail(tunnel_id)


@router.put("/{tunnel_id}", response_model=TunnelRead)
def update_tunnel(
    tunnel_id: int,
    payload: TunnelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TunnelRead:
    tunnel = TunnelService(db).update_tunnel(tunnel_id, payload, user.id)
    db.commit()
    db.refresh(tunnel)
    return TunnelRead.model_validate(tunnel)


@router.delete("/{tunnel_id}")
def delete_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    TunnelService(db).delete_tunnel(tunnel_id, user.id)
    db.commit()
    return {"status": "ok"}


@router.post("/{tunnel_id}/start")
async def start_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    manager=Depends(get_supervisor),
) -> dict:
    TunnelService(db).set_desired_state(tunnel_id, DesiredState.RUNNING, user.id, "start")
    db.commit()
    await manager.run_once([tunnel_id])
    return {"status": "ok"}


@router.post("/{tunnel_id}/stop")
async def stop_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    manager=Depends(get_supervisor),
) -> dict:
    TunnelService(db).set_desired_state(tunnel_id, DesiredState.STOPPED, user.id, "stop")
    db.commit()
    await manager.run_once([tunnel_id])
    return {"status": "ok"}


@router.post("/{tunnel_id}/restart")
async def restart_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    manager=Depends(get_supervisor),
) -> dict:
    service = TunnelService(db)
    service.set_desired_state(tunnel_id, DesiredState.STOPPED, user.id, "stop")
    db.commit()
    await manager.run_once([tunnel_id])

    session_factory = get_session_factory()
    with session_factory() as session:
        TunnelService(session).restart(tunnel_id, user.id)
        session.commit()

    await manager.run_once([tunnel_id])
    return {"status": "ok"}


@router.post("/{tunnel_id}/probe")
async def probe_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    manager=Depends(get_supervisor),
) -> dict:
    runtime = TunnelRuntimeRepository(db).get_or_create(tunnel_id)
    runtime.last_healthcheck_at = None
    db.commit()
    await manager.run_once([tunnel_id])
    return {"status": "ok"}
