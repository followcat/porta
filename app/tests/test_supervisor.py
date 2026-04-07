from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.db.base import utcnow
from app.supervisor.process_registry import ManagedProcess
from app.repositories.runtime_repo import TunnelRuntimeRepository
from app.supervisor.process_registry import ProcessRegistry
from app.supervisor.worker import TunnelWorker
from app.services.ssh_known_hosts_service import KnownHostResult


class FakeProcess:
    def __init__(self, *, pid: int = 1234, returncode: int | None = None, stderr: bytes = b""):
        self.pid = pid
        self.returncode = returncode
        self._stderr = stderr
        self.stderr = FakeStderr(stderr)
        self.terminated = False
        self.killed = False

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = self.returncode if self.returncode is not None else 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def communicate(self):
        return b"", self._stderr


class FakeStderr:
    def __init__(self, data: bytes):
        self._data = data
        self._read = False

    async def read(self, n: int = -1) -> bytes:
        del n
        if self._read:
            await asyncio.sleep(0.1)
            return b""
        self._read = True
        return self._data


async def _noop_sleep(_: float) -> None:
    return None


async def _launch_success(*args, **kwargs):
    del args, kwargs
    return FakeProcess(pid=4321, returncode=None)


async def _launch_auth_failure(*args, **kwargs):
    del args, kwargs
    return FakeProcess(returncode=255, stderr=b"Permission denied")


async def _can_connect_success(host: str, port: int, timeout_ms: int = 1000):
    del host, port, timeout_ms
    return True


async def _can_connect_failure(host: str, port: int, timeout_ms: int = 1000):
    del host, port, timeout_ms
    return False


async def _ensure_known_host(*args, **kwargs):
    del args, kwargs
    return KnownHostResult(added=False, known_hosts_path="/tmp/known_hosts", entries_added=0)


async def _launch_slow_success(*args, **kwargs):
    del args, kwargs
    await asyncio.sleep(0.05)
    return FakeProcess(pid=5555, returncode=None)


@pytest.mark.asyncio
async def test_worker_starts_tunnel(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()
    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_success,
        sleep_func=_noop_sleep,
    )

    worker.port_probe.is_bind_available = lambda host, port: True
    worker.port_probe.can_connect = _can_connect_success
    worker.known_hosts.ensure_known_host = _ensure_known_host

    await worker.reconcile()

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        assert runtime.actual_state == "running"
        assert runtime.pid == 4321
        assert registry.get(seeded_entities["tunnel"].id) is not None


@pytest.mark.asyncio
async def test_worker_marks_auth_failure_as_failed(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()
    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_auth_failure,
        sleep_func=_noop_sleep,
    )

    worker.port_probe.is_bind_available = lambda host, port: True
    worker.known_hosts.ensure_known_host = _ensure_known_host

    await worker.reconcile()

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        assert runtime.actual_state == "failed"
        assert runtime.current_error_code == "AUTH_FAILED"


@pytest.mark.asyncio
async def test_worker_healthcheck_uses_loopback_for_wildcard_bind(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()

    with session_factory() as session:
        tunnel = seeded_entities["tunnel"]
        db_tunnel = session.get(type(tunnel), tunnel.id)
        db_tunnel.bind_address = "0.0.0.0"
        session.commit()

    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_success,
        sleep_func=_noop_sleep,
    )

    calls: list[str] = []

    async def fake_tcp_check(host: str, port: int, timeout_ms: int = 1000):
        del port, timeout_ms
        calls.append(host)
        return SimpleNamespace(ok=True, message="ok")

    worker.healthchecks.tcp_check = fake_tcp_check
    worker.known_hosts.ensure_known_host = _ensure_known_host

    with session_factory() as session:
        db_tunnel = session.get(type(tunnel), tunnel.id)
        result = await worker._run_healthcheck(db_tunnel)

    assert calls
    assert calls[0] == "127.0.0.1"
    assert result.ok is True


@pytest.mark.asyncio
async def test_worker_keeps_starting_state_within_startup_window(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()
    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_success,
        sleep_func=_noop_sleep,
    )

    worker.port_probe.is_bind_available = lambda host, port: True
    worker.port_probe.can_connect = _can_connect_failure
    worker.known_hosts.ensure_known_host = _ensure_known_host

    await worker.reconcile()
    await worker.reconcile()

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        assert runtime.actual_state == "starting"
        assert runtime.current_error_code is None


@pytest.mark.asyncio
async def test_worker_marks_forward_not_ready_after_startup_window(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()
    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_success,
        sleep_func=_noop_sleep,
    )

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        runtime.actual_state = "starting"
        runtime.started_at = utcnow() - timedelta(seconds=20)
        session.commit()

    registry.set(seeded_entities["tunnel"].id, ManagedProcess(process=FakeProcess(pid=9999, returncode=None)))
    worker.port_probe.can_connect = _can_connect_failure
    worker.known_hosts.ensure_known_host = _ensure_known_host

    await worker.reconcile()

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        assert runtime.actual_state == "backoff"
        assert runtime.current_error_code == "FORWARD_NOT_READY"


@pytest.mark.asyncio
async def test_worker_uses_stderr_summary_for_startup_timeout_classification(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()
    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_success,
        sleep_func=_noop_sleep,
    )

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        runtime.actual_state = "starting"
        runtime.started_at = utcnow() - timedelta(seconds=20)
        session.commit()

    registry.set(
        seeded_entities["tunnel"].id,
        ManagedProcess(process=FakeProcess(pid=9999, returncode=None, stderr=b"Permission denied")),
    )
    worker.port_probe.can_connect = _can_connect_failure
    worker.known_hosts.ensure_known_host = _ensure_known_host

    await worker.reconcile()

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        assert runtime.actual_state == "failed"
        assert runtime.current_error_code == "AUTH_FAILED"
        assert "Permission denied" in runtime.current_error_message


@pytest.mark.asyncio
async def test_worker_records_exited_starting_process_before_restart(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()
    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_success,
        sleep_func=_noop_sleep,
    )

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        runtime.actual_state = "starting"
        runtime.started_at = utcnow()
        session.commit()

    registry.set(
        seeded_entities["tunnel"].id,
        ManagedProcess(process=FakeProcess(pid=9999, returncode=255, stderr=b"Permission denied")),
    )
    worker.known_hosts.ensure_known_host = _ensure_known_host

    await worker.reconcile()

    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(seeded_entities["tunnel"].id)
        assert runtime.actual_state == "failed"
        assert runtime.current_error_code == "AUTH_FAILED"


@pytest.mark.asyncio
async def test_worker_serializes_concurrent_reconcile_for_same_tunnel(session_factory, seeded_entities, monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/bin/sh")
    registry = ProcessRegistry()
    worker = TunnelWorker(
        seeded_entities["tunnel"].id,
        session_factory,
        registry,
        process_launcher=_launch_slow_success,
        sleep_func=_noop_sleep,
    )

    calls: list[int] = []

    async def tracked_launch(*args, **kwargs):
        del args, kwargs
        calls.append(1)
        await asyncio.sleep(0.05)
        return FakeProcess(pid=6000 + len(calls), returncode=None)

    worker.process_launcher = tracked_launch
    worker.port_probe.is_bind_available = lambda host, port: True
    worker.port_probe.can_connect = _can_connect_success
    worker.known_hosts.ensure_known_host = _ensure_known_host

    await asyncio.gather(worker.reconcile(), worker.reconcile())

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_process_registry_terminate_all_stops_processes():
    registry = ProcessRegistry()
    first = FakeProcess(pid=7001, returncode=None)
    second = FakeProcess(pid=7002, returncode=None)
    registry.set(1, ManagedProcess(process=first))
    registry.set(2, ManagedProcess(process=second))

    await registry.terminate_all(timeout_seconds=0.01)

    assert first.terminated is True
    assert second.terminated is True
    assert registry.get(1) is None
    assert registry.get(2) is None
