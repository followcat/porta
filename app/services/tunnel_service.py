from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from app.core.enums import ActualState, DesiredState, EventLevel, HealthcheckType
from app.core.exceptions import ResourceConflictError, ValidationError
from app.db.models.tunnel import Tunnel
from app.db.models.tunnel_event import TunnelEvent
from app.repositories.credential_repo import CredentialRepository
from app.repositories.event_repo import TunnelEventRepository
from app.repositories.runtime_repo import TunnelRuntimeRepository
from app.repositories.tunnel_repo import TunnelRepository
from app.schemas.event import TunnelEventRead
from app.schemas.runtime import DashboardSummary, TunnelRuntimeRead
from app.schemas.tunnel import TunnelCreate, TunnelDetailRead, TunnelListFilters, TunnelRead, TunnelUpdate
from app.services.audit_service import AuditService


class TunnelService:
    def __init__(self, session: Session):
        self.session = session
        self.tunnels = TunnelRepository(session)
        self.credentials = CredentialRepository(session)
        self.runtimes = TunnelRuntimeRepository(session)
        self.events = TunnelEventRepository(session)
        self.audit = AuditService(session)

    def list_tunnels(self, filters: TunnelListFilters | None = None) -> list[Tunnel]:
        return self.tunnels.list(filters)

    def get_tunnel(self, tunnel_id: int) -> Tunnel:
        tunnel = self.tunnels.get(tunnel_id)
        if not tunnel:
            raise ValidationError("tunnel not found")
        return tunnel

    def create_tunnel(self, data: TunnelCreate, actor_id: int | None) -> Tunnel:
        data = self._normalize_tunnel_payload(data)
        if self.tunnels.get_by_name(data.name):
            raise ResourceConflictError("tunnel name already exists")
        self._validate_credential_exists(data.credential_id)
        self._validate_tunnel_payload(data)
        tunnel = Tunnel(**data.model_dump())
        tunnel.desired_state = data.desired_state.value
        tunnel.restart_policy = data.restart_policy.value
        tunnel.healthcheck_type = data.healthcheck_type.value
        tunnel.created_by = actor_id
        tunnel.updated_by = actor_id
        self.tunnels.create(tunnel)
        self.runtimes.get_or_create(tunnel.id)
        self.events.add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="tunnel_created",
                level=EventLevel.INFO.value,
                message=f"Tunnel {tunnel.name} created",
            )
        )
        self.audit.log(actor_id, "tunnel_created", "tunnel", str(tunnel.id), {"name": tunnel.name})
        return tunnel

    def update_tunnel(self, tunnel_id: int, data: TunnelUpdate, actor_id: int | None) -> Tunnel:
        data = self._normalize_tunnel_payload(data)
        tunnel = self.get_tunnel(tunnel_id)
        existing_by_name = self.tunnels.get_by_name(data.name)
        if existing_by_name and existing_by_name.id != tunnel.id:
            raise ResourceConflictError("tunnel name already exists")
        self._validate_credential_exists(data.credential_id)
        self._validate_tunnel_payload(data)
        for key, value in data.model_dump().items():
            setattr(tunnel, key, value)
        tunnel.desired_state = data.desired_state.value
        tunnel.restart_policy = data.restart_policy.value
        tunnel.healthcheck_type = data.healthcheck_type.value
        tunnel.updated_by = actor_id
        self.events.add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="tunnel_updated",
                level=EventLevel.INFO.value,
                message=f"Tunnel {tunnel.name} updated",
            )
        )
        self.audit.log(actor_id, "tunnel_updated", "tunnel", str(tunnel.id), {"name": tunnel.name})
        return tunnel

    def delete_tunnel(self, tunnel_id: int, actor_id: int | None) -> None:
        tunnel = self.get_tunnel(tunnel_id)
        runtime = self.runtimes.get_or_create(tunnel.id)
        if runtime.actual_state != ActualState.STOPPED.value:
            raise ValidationError("tunnel must be stopped before deletion")
        self.tunnels.delete(tunnel)
        self.audit.log(actor_id, "tunnel_deleted", "tunnel", str(tunnel.id), {"name": tunnel.name})

    def set_desired_state(self, tunnel_id: int, desired_state: DesiredState, actor_id: int | None, action: str) -> Tunnel:
        tunnel = self.get_tunnel(tunnel_id)
        tunnel.desired_state = desired_state.value
        runtime = self.runtimes.get_or_create(tunnel.id)
        if desired_state == DesiredState.RUNNING:
            runtime.actual_state = ActualState.STOPPED.value
            runtime.next_retry_at = None
            runtime.consecutive_failures = 0
            runtime.current_error_code = None
            runtime.current_error_message = None
        self.events.add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type=f"tunnel_{action}_requested",
                level=EventLevel.INFO.value,
                message=f"Manual {action} requested",
            )
        )
        self.audit.log(actor_id, f"tunnel_{action}", "tunnel", str(tunnel.id), {"name": tunnel.name})
        return tunnel

    def restart(self, tunnel_id: int, actor_id: int | None) -> Tunnel:
        tunnel = self.get_tunnel(tunnel_id)
        tunnel.desired_state = DesiredState.RUNNING.value
        runtime = self.runtimes.get_or_create(tunnel.id)
        runtime.actual_state = ActualState.STOPPED.value
        runtime.next_retry_at = None
        runtime.consecutive_failures = 0
        runtime.current_error_code = None
        runtime.current_error_message = None
        self.events.add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="tunnel_restart_requested",
                level=EventLevel.INFO.value,
                message="Manual restart requested",
            )
        )
        self.audit.log(actor_id, "tunnel_restart", "tunnel", str(tunnel.id), {"name": tunnel.name})
        return tunnel

    def get_detail(self, tunnel_id: int) -> TunnelDetailRead:
        tunnel = self.get_tunnel(tunnel_id)
        runtime = self.runtimes.get_or_create(tunnel.id)
        events = self.events.list_for_tunnel(tunnel.id, limit=50)
        return TunnelDetailRead(
            tunnel=TunnelRead.model_validate(tunnel),
            runtime=TunnelRuntimeRead.model_validate(runtime),
            recent_events=[TunnelEventRead.model_validate(event) for event in events],
        )

    def get_dashboard_summary(self) -> DashboardSummary:
        tunnels = self.tunnels.list()
        counter = Counter((tunnel.runtime.actual_state if tunnel.runtime else ActualState.STOPPED.value) for tunnel in tunnels)
        return DashboardSummary(
            total=len(tunnels),
            running=counter[ActualState.RUNNING.value],
            degraded=counter[ActualState.DEGRADED.value],
            failed=counter[ActualState.FAILED.value],
            stopped=counter[ActualState.STOPPED.value],
            recent_errors=self.events.count_recent_errors(),
        )

    def _validate_credential_exists(self, credential_id: int) -> None:
        if not self.credentials.get(credential_id):
            raise ValidationError("credential not found")

    def _validate_tunnel_payload(self, data: TunnelCreate | TunnelUpdate) -> None:
        if data.bind_address == "0.0.0.0" and not data.allow_gateway_ports:
            raise ValidationError("bind_address 0.0.0.0 requires allow_gateway_ports to be enabled")
        if data.healthcheck_type == HealthcheckType.HTTP and not data.healthcheck_path:
            raise ValidationError("http healthcheck requires healthcheck_path")

    def _normalize_tunnel_payload(self, data: TunnelCreate | TunnelUpdate) -> TunnelCreate | TunnelUpdate:
        if data.bind_address in {"0.0.0.0", "::", "*"} and not data.allow_gateway_ports:
            return data.model_copy(update={"allow_gateway_ports": True})
        return data
