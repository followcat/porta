from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, resolve_executable
from app.core.enums import ActualState, AuthType, DesiredState, EventLevel, HealthcheckType, RestartPolicy
from app.core.exceptions import DependencyMissingError, ValidationError
from app.db.base import utcnow
from app.db.models.tunnel import Tunnel
from app.db.models.tunnel_event import TunnelEvent
from app.db.models.tunnel_runtime import TunnelRuntime
from app.repositories.event_repo import TunnelEventRepository
from app.repositories.runtime_repo import TunnelRuntimeRepository
from app.repositories.tunnel_repo import TunnelRepository
from app.services.credential_service import CredentialService
from app.services.healthcheck_service import HealthcheckService
from app.services.port_probe_service import PortProbeService
from app.services.ssh_command_builder import SSHCommandBuilder
from app.services.ssh_known_hosts_service import SSHKnownHostsService
from app.supervisor.backoff import compute_backoff
from app.supervisor.process_registry import ManagedProcess, ProcessRegistry
from app.supervisor.state_machine import transition

logger = logging.getLogger(__name__)


class TunnelWorker:
    def __init__(
        self,
        tunnel_id: int,
        session_factory: sessionmaker[Session],
        registry: ProcessRegistry,
        *,
        process_launcher: Callable[..., object] | None = None,
        sleep_func: Callable[[float], object] = asyncio.sleep,
    ) -> None:
        self.tunnel_id = tunnel_id
        self.session_factory = session_factory
        self.registry = registry
        self.process_launcher = process_launcher or asyncio.create_subprocess_exec
        self.sleep_func = sleep_func
        self.settings = get_settings()
        self.port_probe = PortProbeService()
        self.healthchecks = HealthcheckService()
        self.command_builder = SSHCommandBuilder()
        self.known_hosts = SSHKnownHostsService()

    async def reconcile(self) -> None:
        async with self.registry.lock_for(self.tunnel_id):
            with self.session_factory() as session:
                tunnel_repo = TunnelRepository(session)
                runtime_repo = TunnelRuntimeRepository(session)
                tunnel = tunnel_repo.get(self.tunnel_id)
                if not tunnel:
                    session.commit()
                    return
                runtime = runtime_repo.get_or_create(self.tunnel_id)

                if tunnel.desired_state == DesiredState.STOPPED.value or not tunnel.enabled:
                    await self.ensure_stopped(session, tunnel, runtime)
                    session.commit()
                    return

                if runtime.actual_state == ActualState.FAILED.value:
                    session.commit()
                    return

                if runtime.actual_state == ActualState.BACKOFF.value and runtime.next_retry_at and utcnow() < runtime.next_retry_at:
                    session.commit()
                    return

                managed = self.registry.get(self.tunnel_id)
                process = managed.process if managed else None
                if process is None or process.returncode is not None:
                    await self.handle_not_running(session, tunnel, runtime, managed)
                    session.commit()
                    return

                await self.perform_checks(session, tunnel, runtime, managed)
                session.commit()

    async def ensure_stopped(self, session: Session, tunnel: Tunnel, runtime: TunnelRuntime) -> None:
        managed = self.registry.get(tunnel.id)
        already_stopped = runtime.actual_state == ActualState.STOPPED.value and managed is None
        if already_stopped:
            runtime.heartbeat_at = utcnow()
            return
        previous_pid = runtime.pid
        runtime.actual_state = transition(runtime.actual_state, ActualState.STOPPING.value)
        if managed:
            await self._terminate_managed(managed)
            self.registry.remove(tunnel.id)
            self._cleanup_temp_key(managed)
        runtime.actual_state = ActualState.STOPPED.value
        runtime.pid = None
        runtime.local_bind_ok = None
        runtime.healthcheck_ok = None
        runtime.current_error_code = None
        runtime.current_error_message = None
        runtime.next_retry_at = None
        runtime.heartbeat_at = utcnow()
        self._event_repo(session).add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="process_stopped",
                level=EventLevel.INFO.value,
                message="Tunnel process stopped",
                detail={
                    "previous_pid": previous_pid,
                    "ssh_target": self._ssh_target(tunnel),
                    "forward": self._forward_description(tunnel),
                },
            )
        )

    async def handle_not_running(
        self,
        session: Session,
        tunnel: Tunnel,
        runtime: TunnelRuntime,
        managed: ManagedProcess | None,
    ) -> None:
        stderr_text = ""
        return_code = None
        if managed and managed.process.returncode is not None:
            return_code = managed.process.returncode
            _, stderr = await managed.process.communicate()
            stderr_text = (stderr or b"").decode("utf-8", errors="ignore").strip()
            self.registry.remove(tunnel.id)
            self._cleanup_temp_key(managed)

            error_code, retryable = self._classify_error(stderr_text, return_code=return_code)
            failure_message = stderr_text or f"SSH process exited with code {return_code}"
            await self._record_failure(
                session,
                tunnel,
                runtime,
                error_code,
                failure_message,
                retryable=retryable,
                return_code=return_code,
            )
            return

        await self._start_process(session, tunnel, runtime, return_code=return_code, stderr_text=stderr_text)

    async def perform_checks(
        self,
        session: Session,
        tunnel: Tunnel,
        runtime: TunnelRuntime,
        managed: ManagedProcess,
    ) -> None:
        process = managed.process
        runtime.pid = process.pid
        runtime.last_seen_at = utcnow()
        runtime.heartbeat_at = utcnow()

        if process.returncode is not None:
            await self.handle_not_running(session, tunnel, runtime, managed)
            return

        local_bind_ok = await self.port_probe.can_connect(tunnel.bind_address, tunnel.local_port, timeout_ms=1000)
        runtime.local_bind_ok = local_bind_ok
        if not local_bind_ok:
            if runtime.actual_state == ActualState.STARTING.value and self._within_startup_window(runtime):
                return
            stderr_summary = await self._read_stderr_summary(process)
            failure_message = self._bind_timeout_message(tunnel, stderr_summary)
            if runtime.actual_state == ActualState.STARTING.value:
                error_code, retryable = self._classify_startup_timeout(stderr_summary)
                await self._record_failure(session, tunnel, runtime, error_code, failure_message, retryable=retryable)
            else:
                await self._record_failure(session, tunnel, runtime, "PORT_CONFLICT", "Local bind check failed", retryable=True)
            await self._terminate_and_unregister(tunnel.id, managed)
            return

        if not self._healthcheck_due(tunnel, runtime):
            if runtime.actual_state != ActualState.DEGRADED.value:
                runtime.actual_state = ActualState.RUNNING.value
            return

        result = await self._run_healthcheck(tunnel)
        runtime.last_healthcheck_at = utcnow()
        runtime.last_healthcheck_message = result.message
        runtime.healthcheck_ok = result.ok
        if result.ok:
            previous = runtime.actual_state
            runtime.actual_state = ActualState.RUNNING.value
            runtime.current_error_code = None
            runtime.current_error_message = None
            if previous == ActualState.DEGRADED.value:
                self._event_repo(session).add(
                    TunnelEvent(
                        tunnel_id=tunnel.id,
                        event_type="healthcheck_recovered",
                        level=EventLevel.INFO.value,
                        message="Healthcheck recovered",
                    )
                )
            return

        if runtime.actual_state == ActualState.DEGRADED.value:
            await self._record_failure(session, tunnel, runtime, "HEALTHCHECK_FAILED", result.message, retryable=True)
            await self._terminate_and_unregister(tunnel.id, managed)
            return

        runtime.actual_state = ActualState.DEGRADED.value
        runtime.current_error_code = "HEALTHCHECK_FAILED"
        runtime.current_error_message = result.message
        self._event_repo(session).add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="healthcheck_failed",
                level=EventLevel.WARN.value,
                message=result.message,
                detail={
                    "healthcheck_type": tunnel.healthcheck_type,
                    "check_host": self.port_probe.local_check_host(tunnel.bind_address),
                    "local_port": tunnel.local_port,
                },
            )
        )

    async def _start_process(
        self,
        session: Session,
        tunnel: Tunnel,
        runtime: TunnelRuntime,
        *,
        return_code: int | None = None,
        stderr_text: str = "",
    ) -> None:
        dependency_issue = self._check_dependencies(tunnel)
        if dependency_issue:
            await self._record_failure(session, tunnel, runtime, *dependency_issue, retryable=False, return_code=return_code)
            return

        if not self.port_probe.is_bind_available(tunnel.bind_address, tunnel.local_port):
            await self._record_failure(session, tunnel, runtime, "PORT_CONFLICT", "Local port is already occupied", retryable=False, return_code=return_code)
            return

        if tunnel.strict_host_key_checking:
            try:
                result = await self.known_hosts.ensure_known_host(tunnel.ssh_host, tunnel.ssh_port)
            except DependencyMissingError as exc:
                await self._record_failure(session, tunnel, runtime, "SSH_KEYSCAN_MISSING", str(exc), retryable=False, return_code=return_code)
                return
            except ValidationError as exc:
                await self._record_failure(session, tunnel, runtime, "HOST_KEY_SCAN_FAILED", str(exc), retryable=True, return_code=return_code)
                return
            else:
                if result.added:
                    self._event_repo(session).add(
                        TunnelEvent(
                            tunnel_id=tunnel.id,
                            event_type="host_key_added",
                            level=EventLevel.INFO.value,
                            message=f"Added {result.entries_added} host key entry to known_hosts",
                            detail={
                                "known_hosts_path": result.known_hosts_path,
                                "ssh_target": self._ssh_target(tunnel),
                            },
                        )
                    )

        credential_service = CredentialService(session)
        decrypted = credential_service.decrypt_credential(tunnel.credential)
        identity_file: str | None = None
        if decrypted.auth_type == AuthType.KEY:
            identity_file = credential_service.write_private_key_tempfile(decrypted)
        try:
            command = self.command_builder.build(
                ssh_host=tunnel.ssh_host,
                ssh_port=tunnel.ssh_port,
                bind_address=tunnel.bind_address,
                local_port=tunnel.local_port,
                remote_host=tunnel.remote_host,
                remote_port=tunnel.remote_port,
                strict_host_key_checking=tunnel.strict_host_key_checking,
                allow_gateway_ports=tunnel.allow_gateway_ports,
                credential=decrypted,
                identity_file=identity_file,
            )
        except Exception:
            if identity_file:
                os.unlink(identity_file)
            raise

        runtime.actual_state = ActualState.STARTING.value
        runtime.command_line = command.masked_command
        runtime.current_error_code = None
        runtime.current_error_message = None
        runtime.started_at = utcnow()
        runtime.last_seen_at = runtime.started_at
        runtime.heartbeat_at = runtime.started_at

        proc = await self.process_launcher(
            *command.argv,
            env={**os.environ, **command.env},
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self.registry.set(tunnel.id, ManagedProcess(process=proc, temp_key_path=identity_file))
        self._event_repo(session).add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="process_started",
                level=EventLevel.INFO.value,
                message=f"SSH tunnel process started (pid={proc.pid})",
                detail={
                    "pid": proc.pid,
                    "command_line": command.masked_command,
                    "ssh_target": self._ssh_target(tunnel),
                    "forward": self._forward_description(tunnel),
                    "healthcheck_type": tunnel.healthcheck_type,
                },
            )
        )
        await self.sleep_func(min(1, self._startup_window_seconds()))

        if proc.returncode is not None:
            _, stderr = await proc.communicate()
            stderr_message = (stderr or b"").decode("utf-8", errors="ignore").strip() or stderr_text
            self.registry.remove(tunnel.id)
            self._cleanup_temp_key(ManagedProcess(process=proc, temp_key_path=identity_file))
            code, retryable = self._classify_error(stderr_message, return_code=proc.returncode)
            await self._record_failure(session, tunnel, runtime, code, stderr_message or "process exited during startup", retryable=retryable, return_code=proc.returncode)
            return

        bind_ok = await self.port_probe.can_connect(tunnel.bind_address, tunnel.local_port, timeout_ms=1000)
        runtime.local_bind_ok = bind_ok
        if not bind_ok:
            return

        self._mark_running(runtime, tunnel, proc.pid)

    async def _record_failure(
        self,
        session: Session,
        tunnel: Tunnel,
        runtime: TunnelRuntime,
        error_code: str,
        message: str,
        *,
        retryable: bool,
        return_code: int | None = None,
    ) -> None:
        runtime.last_exit_at = utcnow()
        runtime.last_exit_code = return_code
        runtime.current_error_code = error_code
        runtime.current_error_message = message[:1000]
        runtime.consecutive_failures += 1
        runtime.pid = None
        runtime.local_bind_ok = False if error_code == "PORT_CONFLICT" else runtime.local_bind_ok

        self._event_repo(session).add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="process_exited" if return_code is not None else "entered_failed",
                level=EventLevel.ERROR.value,
                message=message[:1000],
                detail={
                    "error_code": error_code,
                    "retryable": retryable,
                    "return_code": return_code,
                    "pid": runtime.pid,
                    "command_line": runtime.command_line,
                    "local_bind_ok": runtime.local_bind_ok,
                    "healthcheck_ok": runtime.healthcheck_ok,
                    "ssh_target": self._ssh_target(tunnel),
                    "forward": self._forward_description(tunnel),
                },
            )
        )

        if not retryable or tunnel.restart_policy == RestartPolicy.NEVER.value:
            runtime.actual_state = ActualState.FAILED.value
            runtime.next_retry_at = None
            return

        if tunnel.max_retry_count is not None and runtime.consecutive_failures > tunnel.max_retry_count:
            runtime.actual_state = ActualState.FAILED.value
            runtime.next_retry_at = None
            return

        runtime.actual_state = ActualState.BACKOFF.value
        delay_seconds = compute_backoff(
            tunnel.restart_backoff_seconds,
            runtime.consecutive_failures,
            tunnel.max_restart_backoff_seconds,
        )
        runtime.next_retry_at = utcnow().replace(microsecond=0) + timedelta(seconds=delay_seconds)
        self._event_repo(session).add(
            TunnelEvent(
                tunnel_id=tunnel.id,
                event_type="entered_backoff",
                level=EventLevel.WARN.value,
                message=f"Retry scheduled in {delay_seconds}s",
                detail={
                    "error_code": error_code,
                    "delay_seconds": delay_seconds,
                    "next_retry_at": runtime.next_retry_at.isoformat() if runtime.next_retry_at else None,
                },
            )
        )

    async def _terminate_and_unregister(self, tunnel_id: int, managed: ManagedProcess) -> None:
        await self._terminate_managed(managed)
        self.registry.remove(tunnel_id)
        self._cleanup_temp_key(managed)

    async def _terminate_managed(self, managed: ManagedProcess) -> None:
        process = managed.process
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    def _cleanup_temp_key(self, managed: ManagedProcess) -> None:
        if managed.temp_key_path and os.path.exists(managed.temp_key_path):
            os.unlink(managed.temp_key_path)

    def _check_dependencies(self, tunnel: Tunnel) -> tuple[str, str] | None:
        ssh_bin = resolve_executable(self.settings.ssh_bin, "ssh")
        if not ssh_bin:
            return "SSH_BIN_MISSING", f"ssh executable not found (configured: {self.settings.ssh_bin})"
        if tunnel.strict_host_key_checking:
            ssh_keyscan_bin = resolve_executable(self.settings.ssh_keyscan_bin, "ssh-keyscan")
            if not ssh_keyscan_bin:
                return "SSH_KEYSCAN_MISSING", f"ssh-keyscan executable not found (configured: {self.settings.ssh_keyscan_bin})"
        if tunnel.credential.auth_type == "password":
            sshpass_bin = resolve_executable(self.settings.sshpass_bin, "sshpass")
            if not sshpass_bin:
                return "SSHPASS_MISSING", f"sshpass executable not found (configured: {self.settings.sshpass_bin})"
        return None

    def _healthcheck_due(self, tunnel: Tunnel, runtime: TunnelRuntime) -> bool:
        if tunnel.healthcheck_type == HealthcheckType.NONE.value:
            return False
        if runtime.last_healthcheck_at is None:
            return True
        delta = utcnow() - runtime.last_healthcheck_at
        return delta.total_seconds() >= tunnel.healthcheck_interval_seconds

    async def _run_healthcheck(self, tunnel: Tunnel):
        check_host = self.port_probe.local_check_host(tunnel.bind_address)
        if tunnel.healthcheck_type == HealthcheckType.TCP.value:
            return await self.healthchecks.tcp_check(check_host, tunnel.local_port, tunnel.healthcheck_timeout_ms)
        url = f"http://{check_host}:{tunnel.local_port}{tunnel.healthcheck_path or '/'}"
        return await self.healthchecks.http_check(url, tunnel.healthcheck_timeout_ms)

    def _classify_error(self, message: str, *, return_code: int | None) -> tuple[str, bool]:
        lower = message.lower()
        if "permission denied" in lower or "authentication failed" in lower:
            return "AUTH_FAILED", False
        if "host key verification failed" in lower and "no " in lower and "host key is known" in lower:
            return "HOST_KEY_UNKNOWN", False
        if "host key verification failed" in lower:
            return "HOST_KEY_FAILED", False
        if "name or service not known" in lower or "temporary failure in name resolution" in lower:
            return "DNS_FAILED", True
        if "connection reset" in lower or "connection timed out" in lower or "connection refused" in lower:
            return "REMOTE_UNREACHABLE", True
        if return_code is not None:
            return "PROCESS_EXITED", True
        return "PROCESS_EXITED", True

    def _event_repo(self, session: Session) -> TunnelEventRepository:
        return TunnelEventRepository(session)

    def _ssh_target(self, tunnel: Tunnel) -> str:
        return f"{tunnel.credential.username}@{tunnel.ssh_host}:{tunnel.ssh_port}"

    def _forward_description(self, tunnel: Tunnel) -> str:
        return f"{tunnel.bind_address}:{tunnel.local_port} -> {tunnel.remote_host}:{tunnel.remote_port}"

    def _mark_running(self, runtime: TunnelRuntime, tunnel: Tunnel, pid: int) -> None:
        runtime.actual_state = ActualState.RUNNING.value
        runtime.pid = pid
        runtime.last_seen_at = utcnow()
        runtime.heartbeat_at = utcnow()
        runtime.local_bind_ok = True
        runtime.healthcheck_ok = True if tunnel.healthcheck_type == HealthcheckType.NONE.value else runtime.healthcheck_ok
        runtime.current_error_code = None
        runtime.current_error_message = None
        runtime.consecutive_failures = 0
        runtime.next_retry_at = None
        runtime.restart_count += 1

    def _startup_window_seconds(self) -> int:
        return max(15, self.settings.tunnel_startup_grace_seconds)

    def _within_startup_window(self, runtime: TunnelRuntime) -> bool:
        if runtime.started_at is None:
            return False
        delta = utcnow() - runtime.started_at
        return delta.total_seconds() < self._startup_window_seconds()

    def _bind_timeout_message(self, tunnel: Tunnel, stderr_summary: str = "") -> str:
        check_host = self.port_probe.local_check_host(tunnel.bind_address)
        message = (
            f"Local forward {check_host}:{tunnel.local_port} did not accept connections "
            f"within {self._startup_window_seconds()}s"
        )
        if stderr_summary:
            message = f"{message}. SSH stderr: {stderr_summary}"
        return message

    async def _read_stderr_summary(self, process: asyncio.subprocess.Process, limit: int = 1024) -> str:
        stream = process.stderr
        if stream is None:
            return ""

        chunks: list[bytes] = []
        total = 0
        while total < limit:
            try:
                chunk = await asyncio.wait_for(stream.read(min(256, limit - total)), timeout=0.05)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)

        text = b"".join(chunks).decode("utf-8", errors="ignore").strip()
        text = " ".join(text.split())
        return text[:limit]

    def _classify_startup_timeout(self, stderr_summary: str) -> tuple[str, bool]:
        if not stderr_summary:
            return "FORWARD_NOT_READY", True
        code, retryable = self._classify_error(stderr_summary, return_code=None)
        if code == "PROCESS_EXITED":
            return "FORWARD_NOT_READY", True
        return code, retryable
