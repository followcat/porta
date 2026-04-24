from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.tunnel import Tunnel
from app.db.models.tunnel_runtime import TunnelRuntime
from app.schemas.tunnel import TunnelListFilters


class TunnelRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, filters: TunnelListFilters | None = None) -> list[Tunnel]:
        stmt = select(Tunnel).options(joinedload(Tunnel.runtime), joinedload(Tunnel.credential)).order_by(Tunnel.name)
        if filters:
            if filters.group_name:
                stmt = stmt.where(Tunnel.group_name == filters.group_name)
            if filters.desired_state:
                stmt = stmt.where(Tunnel.desired_state == filters.desired_state)
            if filters.enabled is not None:
                stmt = stmt.where(Tunnel.enabled == filters.enabled)
            if filters.keyword:
                pattern = f"%{filters.keyword}%"
                stmt = stmt.where(
                    or_(
                        Tunnel.name.ilike(pattern),
                        Tunnel.description.ilike(pattern),
                        Tunnel.ssh_host.ilike(pattern),
                        Tunnel.remote_host.ilike(pattern),
                    )
                )
            if filters.actual_state:
                stmt = stmt.join(TunnelRuntime, isouter=True).where(TunnelRuntime.actual_state == filters.actual_state)
        return list(self.session.scalars(stmt).unique())

    def list_enabled(self) -> list[Tunnel]:
        stmt = (
            select(Tunnel)
            .options(joinedload(Tunnel.runtime), joinedload(Tunnel.credential))
            .where(Tunnel.enabled.is_(True))
            .order_by(Tunnel.id)
        )
        return list(self.session.scalars(stmt).unique())

    def get(self, tunnel_id: int) -> Tunnel | None:
        stmt = (
            select(Tunnel)
            .options(joinedload(Tunnel.runtime), joinedload(Tunnel.credential))
            .where(Tunnel.id == tunnel_id)
        )
        return self.session.scalar(stmt)

    def get_by_name(self, name: str) -> Tunnel | None:
        return self.session.scalar(select(Tunnel).where(Tunnel.name == name))

    def get_by_bind_local_port(self, bind_address: str, local_port: int) -> Tunnel | None:
        stmt = select(Tunnel).where(
            Tunnel.bind_address == bind_address,
            Tunnel.local_port == local_port,
        )
        return self.session.scalar(stmt)

    def create(self, tunnel: Tunnel) -> Tunnel:
        self.session.add(tunnel)
        self.session.flush()
        return tunnel

    def delete(self, tunnel: Tunnel) -> None:
        self.session.delete(tunnel)
