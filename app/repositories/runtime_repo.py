from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import ActualState
from app.db.models.tunnel_runtime import TunnelRuntime


class TunnelRuntimeRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, tunnel_id: int) -> TunnelRuntime | None:
        return self.session.get(TunnelRuntime, tunnel_id)

    def get_or_create(self, tunnel_id: int) -> TunnelRuntime:
        runtime = self.get(tunnel_id)
        if runtime:
            return runtime
        runtime = TunnelRuntime(tunnel_id=tunnel_id, actual_state=ActualState.STOPPED.value)
        self.session.add(runtime)
        self.session.flush()
        return runtime
