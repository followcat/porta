from __future__ import annotations

from app.core.enums import ActualState
from app.core.exceptions import ValidationError

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ActualState.STOPPED.value: {ActualState.STARTING.value},
    ActualState.STARTING.value: {ActualState.RUNNING.value, ActualState.BACKOFF.value},
    ActualState.RUNNING.value: {ActualState.DEGRADED.value, ActualState.BACKOFF.value},
    ActualState.DEGRADED.value: {ActualState.RUNNING.value, ActualState.BACKOFF.value},
    ActualState.BACKOFF.value: {ActualState.STARTING.value, ActualState.FAILED.value},
    ActualState.FAILED.value: {ActualState.STARTING.value},
    ActualState.STOPPING.value: {ActualState.STOPPED.value},
}


def transition(current: str, target: str) -> str:
    if current == target:
        return target
    if target == ActualState.STOPPING.value:
        return target
    if current == ActualState.STOPPING.value and target == ActualState.STOPPED.value:
        return target
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValidationError(f"invalid state transition: {current} -> {target}")
    return target
