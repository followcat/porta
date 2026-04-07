from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import audit, auth, credentials, dashboard, events, tunnels
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    PortaError,
    ResourceConflictError,
    ValidationError,
)
from app.core.logging import configure_logging
from app.db.session import get_session_factory, init_db
from app.repositories.tunnel_repo import TunnelRepository
from app.supervisor.manager import SupervisorManager
from app.supervisor.process_registry import ProcessRegistry
from app.supervisor.worker import TunnelWorker
from app.web.routes import router as web_router

settings = get_settings()


def _enabled_tunnel_ids() -> list[int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        return [tunnel.id for tunnel in TunnelRepository(session).list_enabled()]


def _build_supervisor_manager(registry: ProcessRegistry) -> SupervisorManager:
    session_factory = get_session_factory()
    return SupervisorManager(
        enabled_tunnel_ids_provider=_enabled_tunnel_ids,
        worker_factory=lambda tunnel_id: TunnelWorker(tunnel_id, session_factory, registry),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    if settings.auto_create_tables:
        init_db()
    registry = ProcessRegistry()
    manager = _build_supervisor_manager(registry)
    app.state.registry = registry
    app.state.supervisor_manager = manager
    task = asyncio.create_task(manager.run_forever(), name="porta-supervisor")
    try:
        yield
    finally:
        manager.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(credentials.router, prefix="/api/v1")
app.include_router(tunnels.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(web_router)


@app.exception_handler(AuthenticationError)
async def handle_authentication_error(_: Request, exc: AuthenticationError):
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(AuthorizationError)
async def handle_authorization_error(_: Request, exc: AuthorizationError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(ResourceConflictError)
async def handle_conflict_error(_: Request, exc: ResourceConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def handle_validation_error(_: Request, exc: ValidationError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(PortaError)
async def handle_porta_error(_: Request, exc: PortaError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
