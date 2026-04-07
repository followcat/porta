from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import DesiredState, HealthcheckType, RestartPolicy
from app.schemas.event import TunnelEventRead
from app.schemas.runtime import TunnelRuntimeRead


class TunnelBase(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    ssh_host: str
    ssh_port: int = 22
    credential_id: int
    bind_address: str = "127.0.0.1"
    local_port: int
    remote_host: str
    remote_port: int
    group_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    auto_start: bool = True
    desired_state: DesiredState = DesiredState.RUNNING
    restart_policy: RestartPolicy = RestartPolicy.ALWAYS
    restart_backoff_seconds: int = 5
    max_restart_backoff_seconds: int = 300
    max_retry_count: int | None = None
    check_interval_seconds: int = 10
    healthcheck_type: HealthcheckType = HealthcheckType.TCP
    healthcheck_path: str | None = None
    healthcheck_timeout_ms: int = 3000
    healthcheck_interval_seconds: int = 15
    strict_host_key_checking: bool = True
    allow_gateway_ports: bool = False

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return list(value)

    @field_validator("healthcheck_path")
    @classmethod
    def http_path_requires_value(cls, value: str | None) -> str | None:
        if value and not value.startswith("/"):
            return "/" + value
        return value


class TunnelCreate(TunnelBase):
    pass


class TunnelUpdate(TunnelBase):
    pass


class TunnelRead(TunnelBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class TunnelDetailRead(BaseModel):
    tunnel: TunnelRead
    runtime: TunnelRuntimeRead | None
    recent_events: list[TunnelEventRead]


class TunnelListItem(BaseModel):
    tunnel: TunnelRead
    runtime: TunnelRuntimeRead | None


class TunnelListFilters(BaseModel):
    group_name: str | None = None
    actual_state: str | None = None
    desired_state: str | None = None
    enabled: bool | None = None
    keyword: str | None = None
