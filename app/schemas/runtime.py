from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import ActualState


class TunnelRuntimeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tunnel_id: int
    actual_state: ActualState
    pid: int | None
    command_line: str | None
    started_at: datetime | None
    last_seen_at: datetime | None
    last_exit_at: datetime | None
    last_exit_code: int | None
    restart_count: int
    consecutive_failures: int
    local_bind_ok: bool | None
    healthcheck_ok: bool | None
    last_healthcheck_at: datetime | None
    last_healthcheck_message: str | None
    current_error_code: str | None
    current_error_message: str | None
    next_retry_at: datetime | None
    heartbeat_at: datetime | None
    updated_at: datetime


class DashboardSummary(BaseModel):
    total: int
    running: int
    degraded: int
    failed: int
    stopped: int
    recent_errors: int
