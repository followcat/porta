from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.core.enums import DesiredState
from app.db.models.user import User
from app.db.session import get_session_factory
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.event_repo import TunnelEventRepository
from app.repositories.runtime_repo import TunnelRuntimeRepository
from app.repositories.user_repo import UserRepository
from app.schemas.credential import CredentialCreate, CredentialUpdate
from app.schemas.tunnel import TunnelCreate, TunnelListFilters, TunnelUpdate
from app.services.auth_service import AuthService
from app.services.credential_service import CredentialService
from app.services.tunnel_service import TunnelService

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(get_settings().template_dir))


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(url=path, status_code=303)


def _to_bool(value: object) -> bool:
    return str(value).lower() in {"1", "true", "on", "yes"}


def _current_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    session_factory = get_session_factory()
    with session_factory() as session:
        return UserRepository(session).get(int(user_id))


def _common_context(request: Request, user: User | None, **kwargs) -> dict:
    return {"request": request, "current_user": user, **kwargs}


def _local_check_host(bind_address: str) -> str:
    if bind_address in {"0.0.0.0", "::", "*", ""}:
        return "127.0.0.1"
    return bind_address


def _runtime_hint(detail) -> dict | None:
    runtime = detail.runtime
    if not runtime or not runtime.current_error_message:
        return None

    message = runtime.current_error_message
    lower = message.lower()
    target = f"{detail.tunnel.ssh_host}:{detail.tunnel.ssh_port}"

    if "host key verification failed" in lower and "no " in lower and "host key is known" in lower:
        return {
            "kind": "warn",
            "title": "First-time SSH host key trust is required",
            "body": (
                f"Porta now preloads host keys with ssh-keyscan before connecting in strict mode. "
                f"If this warning appears again for {target}, the service user likely cannot write "
                f"its known_hosts file or the scan failed."
            ),
        }

    if "ssh-keyscan" in lower or "host key scan" in lower:
        return {
            "kind": "warn",
            "title": "Automatic host-key preload failed",
            "body": (
                f"Porta tried to fetch the SSH host key for {target} before connecting, but the pre-check failed. "
                f"Review network reachability and the service user's known_hosts permissions."
            ),
        }

    if "host key verification failed" in lower:
        return {
            "kind": "error",
            "title": "SSH host key mismatch detected",
            "body": (
                f"The host key for {target} does not match the existing known_hosts entry. Review and clean the "
                f"service user's ~/.ssh/known_hosts before retrying."
            ),
        }

    if "permission denied" in lower or "authentication failed" in lower:
        return {
            "kind": "error",
            "title": "SSH authentication failed",
            "body": (
                "The tunnel reached the SSH server, but the username, password, key, or passphrase was rejected."
            ),
        }

    return None


def _runtime_status(detail) -> dict:
    runtime = detail.runtime
    tunnel = detail.tunnel

    if not runtime:
        return {
            "kind": "info",
            "title": "Runtime state is not initialized yet",
            "body": "Porta has not created a runtime snapshot for this tunnel yet.",
        }

    check_host = _local_check_host(tunnel.bind_address)
    state = runtime.actual_state.value if hasattr(runtime.actual_state, "value") else str(runtime.actual_state)

    if state == "starting":
        return {
            "kind": "info",
            "title": "Tunnel is still starting",
            "body": (
                f"SSH process pid {runtime.pid or '—'} is alive. Porta is waiting for the local forward "
                f"{check_host}:{tunnel.local_port} to accept connections."
            ),
        }

    if state == "running":
        health_text = "healthcheck passed" if runtime.healthcheck_ok else "healthcheck pending or disabled"
        return {
            "kind": "success",
            "title": "Tunnel is ready",
            "body": (
                f"Local forward {check_host}:{tunnel.local_port} is reachable and {health_text}."
            ),
        }

    if state == "degraded":
        return {
            "kind": "warn",
            "title": "Tunnel is partially working",
            "body": runtime.current_error_message or "The SSH process is alive, but runtime checks are failing.",
        }

    if state == "backoff":
        next_retry = runtime.next_retry_at.strftime("%Y-%m-%d %H:%M:%S") if runtime.next_retry_at else "unknown"
        return {
            "kind": "warn",
            "title": "Tunnel is waiting before retry",
            "body": (
                f"Last check failed. Porta will retry automatically at {next_retry}. "
                f"{runtime.current_error_message or ''}".strip()
            ),
        }

    if state == "failed":
        return {
            "kind": "error",
            "title": "Tunnel is in failed state",
            "body": runtime.current_error_message or "Automatic retries are paused until you restart or edit the tunnel.",
        }

    if state == "stopped":
        return {
            "kind": "info",
            "title": "Tunnel is stopped",
            "body": "Desired state is stopped, or the tunnel has been terminated intentionally.",
        }

    return {
        "kind": "info",
        "title": f"Current state: {state}",
        "body": runtime.current_error_message or "No additional runtime detail is available.",
    }


def _runtime_snapshot(detail) -> dict:
    runtime = detail.runtime
    tunnel = detail.tunnel
    check_host = _local_check_host(tunnel.bind_address)
    return {
        "ssh_target": f"{tunnel.ssh_host}:{tunnel.ssh_port}",
        "forward": f"{tunnel.bind_address}:{tunnel.local_port} -> {tunnel.remote_host}:{tunnel.remote_port}",
        "local_check_target": f"{check_host}:{tunnel.local_port}",
        "healthcheck": f"{tunnel.healthcheck_type}{(' ' + tunnel.healthcheck_path) if tunnel.healthcheck_path else ''}",
        "command_line": runtime.command_line if runtime else None,
        "last_exit_code": runtime.last_exit_code if runtime else None,
    }


def _parse_tunnel_payload(form) -> TunnelCreate | TunnelUpdate:
    return TunnelCreate(
        name=str(form.get("name", "")).strip(),
        description=str(form.get("description", "")).strip() or None,
        enabled=_to_bool(form.get("enabled", "")),
        ssh_host=str(form.get("ssh_host", "")).strip(),
        ssh_port=int(form.get("ssh_port", 22)),
        credential_id=int(form.get("credential_id")),
        bind_address=str(form.get("bind_address", "127.0.0.1")).strip(),
        local_port=int(form.get("local_port")),
        remote_host=str(form.get("remote_host", "")).strip(),
        remote_port=int(form.get("remote_port")),
        group_name=str(form.get("group_name", "")).strip() or None,
        tags=str(form.get("tags", "")).strip(),
        auto_start=_to_bool(form.get("auto_start", "")),
        desired_state=str(form.get("desired_state", DesiredState.RUNNING.value)),
        restart_policy=str(form.get("restart_policy", "always")),
        restart_backoff_seconds=int(form.get("restart_backoff_seconds", 5)),
        max_restart_backoff_seconds=int(form.get("max_restart_backoff_seconds", 300)),
        max_retry_count=int(form.get("max_retry_count")) if form.get("max_retry_count") else None,
        check_interval_seconds=int(form.get("check_interval_seconds", 10)),
        healthcheck_type=str(form.get("healthcheck_type", "tcp")),
        healthcheck_path=str(form.get("healthcheck_path", "")).strip() or None,
        healthcheck_timeout_ms=int(form.get("healthcheck_timeout_ms", 3000)),
        healthcheck_interval_seconds=int(form.get("healthcheck_interval_seconds", 15)),
        strict_host_key_checking=_to_bool(form.get("strict_host_key_checking", "")),
        allow_gateway_ports=_to_bool(form.get("allow_gateway_ports", "")),
    )


def _parse_credential_payload(form) -> CredentialCreate | CredentialUpdate:
    return CredentialCreate(
        name=str(form.get("name", "")).strip(),
        auth_type=str(form.get("auth_type", "password")),
        username=str(form.get("username", "")).strip(),
        password=str(form.get("password", "")).strip() or None,
        private_key=str(form.get("private_key", "")).strip() or None,
        passphrase=str(form.get("passphrase", "")).strip() or None,
        description=str(form.get("description", "")).strip() or None,
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _redirect("/dashboard" if request.session.get("user_id") else "/login")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user_id"):
        return _redirect("/dashboard")
    return templates.TemplateResponse("login.html", _common_context(request, None, error=None))


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            user = AuthService(session).authenticate(str(form.get("username", "")), str(form.get("password", "")))
            session.commit()
        except Exception as exc:
            session.rollback()
            return templates.TemplateResponse("login.html", _common_context(request, None, error=str(exc)), status_code=400)
    request.session["user_id"] = user.id
    return _redirect("/dashboard")


@router.post("/logout")
def logout_submit(request: Request):
    request.session.clear()
    return _redirect("/login")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        tunnel_service = TunnelService(session)
        all_tunnels = tunnel_service.list_tunnels()
        context = _common_context(
            request,
            user,
            summary=tunnel_service.get_dashboard_summary(),
            recent_events=TunnelEventRepository(session).list_recent(limit=10),
            busiest_tunnels=sorted(all_tunnels, key=lambda item: (item.runtime.restart_count if item.runtime else 0), reverse=True)[:5],
        )
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/tunnels", response_class=HTMLResponse)
def tunnel_list(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    filters = TunnelListFilters(
        group_name=request.query_params.get("group_name"),
        actual_state=request.query_params.get("actual_state"),
        desired_state=request.query_params.get("desired_state"),
        enabled=_to_bool(request.query_params["enabled"]) if "enabled" in request.query_params else None,
        keyword=request.query_params.get("keyword"),
    )
    session_factory = get_session_factory()
    with session_factory() as session:
        tunnels = TunnelService(session).list_tunnels(filters)
    return templates.TemplateResponse("tunnels/list.html", _common_context(request, user, tunnels=tunnels, filters=filters))


@router.get("/tunnels/new", response_class=HTMLResponse)
def tunnel_new_page(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        credentials = CredentialService(session).list_credentials()
    return templates.TemplateResponse("tunnels/form.html", _common_context(request, user, tunnel=None, credentials=credentials, error=None))


@router.post("/tunnels/new")
async def tunnel_create(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    form = await request.form()
    payload = _parse_tunnel_payload(form)
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            TunnelService(session).create_tunnel(payload, user.id)
            session.commit()
        except Exception as exc:
            session.rollback()
            credentials = CredentialService(session).list_credentials()
            return templates.TemplateResponse("tunnels/form.html", _common_context(request, user, tunnel=None, credentials=credentials, error=str(exc)), status_code=400)
    return _redirect("/tunnels")


@router.get("/tunnels/{tunnel_id}", response_class=HTMLResponse)
def tunnel_detail(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        detail = TunnelService(session).get_detail(tunnel_id)
    return templates.TemplateResponse(
        "tunnels/detail.html",
        _common_context(
            request,
            user,
            detail=detail,
            runtime_hint=_runtime_hint(detail),
            runtime_status=_runtime_status(detail),
            runtime_snapshot=_runtime_snapshot(detail),
        ),
    )


@router.get("/tunnels/{tunnel_id}/logs", response_class=HTMLResponse)
def tunnel_log_panel(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        detail = TunnelService(session).get_detail(tunnel_id)
    return templates.TemplateResponse(
        "tunnels/log_panel.html",
        _common_context(
            request,
            user,
            detail=detail,
            runtime_hint=_runtime_hint(detail),
            runtime_status=_runtime_status(detail),
            runtime_snapshot=_runtime_snapshot(detail),
        ),
    )


@router.get("/tunnels/{tunnel_id}/edit", response_class=HTMLResponse)
def tunnel_edit_page(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        tunnel = TunnelService(session).get_tunnel(tunnel_id)
        credentials = CredentialService(session).list_credentials()
    return templates.TemplateResponse("tunnels/form.html", _common_context(request, user, tunnel=tunnel, credentials=credentials, error=None))


@router.post("/tunnels/{tunnel_id}/edit")
async def tunnel_update(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    form = await request.form()
    payload = TunnelUpdate.model_validate(_parse_tunnel_payload(form).model_dump())
    auto_restart = True
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            service = TunnelService(session)
            existing = service.get_tunnel(tunnel_id)
            should_restart = (
                existing.desired_state == DesiredState.RUNNING.value
                or (existing.runtime and existing.runtime.actual_state in {"running", "starting", "degraded", "backoff"})
            )
            service.update_tunnel(tunnel_id, payload, user.id)
            session.commit()
        except Exception as exc:
            session.rollback()
            tunnel = TunnelService(session).get_tunnel(tunnel_id)
            credentials = CredentialService(session).list_credentials()
            return templates.TemplateResponse("tunnels/form.html", _common_context(request, user, tunnel=tunnel, credentials=credentials, error=str(exc)), status_code=400)
    if auto_restart and should_restart:
        manager = request.app.state.supervisor_manager
        with session_factory() as session:
            TunnelService(session).set_desired_state(tunnel_id, DesiredState.STOPPED, user.id, "stop")
            session.commit()
        await manager.run_once([tunnel_id])
        with session_factory() as session:
            TunnelService(session).restart(tunnel_id, user.id)
            session.commit()
        await manager.run_once([tunnel_id])
    return _redirect(f"/tunnels/{tunnel_id}")


@router.post("/tunnels/{tunnel_id}/delete")
async def tunnel_delete(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        TunnelService(session).delete_tunnel(tunnel_id, user.id)
        session.commit()
    return _redirect("/tunnels")


@router.post("/tunnels/{tunnel_id}/start")
async def tunnel_start(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    manager = request.app.state.supervisor_manager
    session_factory = get_session_factory()
    with session_factory() as session:
        TunnelService(session).set_desired_state(tunnel_id, DesiredState.RUNNING, user.id, "start")
        session.commit()
    await manager.run_once([tunnel_id])
    return _redirect(f"/tunnels/{tunnel_id}")


@router.post("/tunnels/{tunnel_id}/stop")
async def tunnel_stop(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    manager = request.app.state.supervisor_manager
    session_factory = get_session_factory()
    with session_factory() as session:
        TunnelService(session).set_desired_state(tunnel_id, DesiredState.STOPPED, user.id, "stop")
        session.commit()
    await manager.run_once([tunnel_id])
    return _redirect(f"/tunnels/{tunnel_id}")


@router.post("/tunnels/{tunnel_id}/restart")
async def tunnel_restart(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    manager = request.app.state.supervisor_manager
    session_factory = get_session_factory()
    with session_factory() as session:
        TunnelService(session).set_desired_state(tunnel_id, DesiredState.STOPPED, user.id, "stop")
        session.commit()
    await manager.run_once([tunnel_id])
    with session_factory() as session:
        TunnelService(session).restart(tunnel_id, user.id)
        session.commit()
    await manager.run_once([tunnel_id])
    return _redirect(f"/tunnels/{tunnel_id}")


@router.post("/tunnels/{tunnel_id}/probe")
async def tunnel_probe(request: Request, tunnel_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    manager = request.app.state.supervisor_manager
    session_factory = get_session_factory()
    with session_factory() as session:
        runtime = TunnelRuntimeRepository(session).get_or_create(tunnel_id)
        runtime.last_healthcheck_at = None
        session.commit()
    await manager.run_once([tunnel_id])
    return _redirect(f"/tunnels/{tunnel_id}")


@router.get("/credentials", response_class=HTMLResponse)
def credential_list(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        credentials = CredentialService(session).list_credentials()
    return templates.TemplateResponse("credentials/list.html", _common_context(request, user, credentials=credentials))


@router.get("/credentials/new", response_class=HTMLResponse)
def credential_new_page(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    return templates.TemplateResponse("credentials/form.html", _common_context(request, user, credential=None, error=None))


@router.post("/credentials/new")
async def credential_create(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    form = await request.form()
    payload = _parse_credential_payload(form)
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            CredentialService(session).create_credential(payload, user.id)
            session.commit()
        except Exception as exc:
            session.rollback()
            return templates.TemplateResponse("credentials/form.html", _common_context(request, user, credential=None, error=str(exc)), status_code=400)
    return _redirect("/credentials")


@router.get("/credentials/{credential_id}/edit", response_class=HTMLResponse)
def credential_edit_page(request: Request, credential_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        credential = CredentialService(session).get_credential(credential_id)
    return templates.TemplateResponse("credentials/form.html", _common_context(request, user, credential=credential, error=None))


@router.post("/credentials/{credential_id}/edit")
async def credential_update(request: Request, credential_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    form = await request.form()
    payload = CredentialUpdate.model_validate(_parse_credential_payload(form).model_dump())
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            CredentialService(session).update_credential(credential_id, payload, user.id)
            session.commit()
        except Exception as exc:
            session.rollback()
            credential = CredentialService(session).get_credential(credential_id)
            return templates.TemplateResponse("credentials/form.html", _common_context(request, user, credential=credential, error=str(exc)), status_code=400)
    return _redirect("/credentials")


@router.post("/credentials/{credential_id}/delete")
async def credential_delete(request: Request, credential_id: int):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        CredentialService(session).delete_credential(credential_id, user.id)
        session.commit()
    return _redirect("/credentials")


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request):
    user = _current_user(request)
    if not user:
        return _redirect("/login")
    session_factory = get_session_factory()
    with session_factory() as session:
        logs = AuditLogRepository(session).list_recent(limit=200)
    return templates.TemplateResponse("audit.html", _common_context(request, user, logs=logs))
