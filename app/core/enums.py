from __future__ import annotations

from enum import Enum


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class UserRole(StringEnum):
    ADMIN = "admin"


class AuthType(StringEnum):
    PASSWORD = "password"
    KEY = "key"


class DesiredState(StringEnum):
    RUNNING = "running"
    STOPPED = "stopped"


class ActualState(StringEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    BACKOFF = "backoff"
    FAILED = "failed"
    STOPPING = "stopping"


class RestartPolicy(StringEnum):
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    NEVER = "never"


class HealthcheckType(StringEnum):
    NONE = "none"
    TCP = "tcp"
    HTTP = "http"


class EventLevel(StringEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
