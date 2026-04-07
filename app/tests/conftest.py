from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.schemas.credential import CredentialCreate
from app.schemas.tunnel import TunnelCreate
from app.services.auth_service import AuthService
from app.services.credential_service import CredentialService
from app.services.tunnel_service import TunnelService


@pytest.fixture(autouse=True)
def clear_cached_settings():
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture
def session_factory(monkeypatch) -> sessionmaker:
    monkeypatch.setenv("PORTA_MASTER_KEY", "test-master-key")
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def seeded_entities(session_factory):
    with session_factory() as session:
        admin = AuthService(session).create_admin("admin", "secret-password")
        credential = CredentialService(session).create_credential(
            CredentialCreate(
                name="server-key",
                auth_type="key",
                username="deployer",
                private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----",
                passphrase=None,
            ),
            admin.id,
        )
        tunnel = TunnelService(session).create_tunnel(
            TunnelCreate(
                name="alpha",
                ssh_host="example.com",
                ssh_port=22,
                credential_id=credential.id,
                bind_address="127.0.0.1",
                local_port=18080,
                remote_host="127.0.0.1",
                remote_port=8080,
                group_name="prod",
                tags=["api"],
            ),
            admin.id,
        )
        session.commit()
        return {"admin": admin, "credential": credential, "tunnel": tunnel}


@pytest_asyncio.fixture
async def api_client(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "porta-test.db"
    monkeypatch.setenv("MYSQL_DSN", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PORTA_MASTER_KEY", "test-master-key")
    monkeypatch.setenv("AUTO_CREATE_TABLES", "true")
    monkeypatch.setenv("SUPERVISOR_LOOP_SECONDS", "3600")

    import app.main as app_main

    importlib.reload(app_main)
    app_main.init_db()
    app_main.app.state.supervisor_manager = SimpleNamespace(run_once=None)

    session_factory = app_main.get_session_factory()
    with session_factory() as session:
        admin = AuthService(session).create_admin("admin", "secret-password")
        credential = CredentialService(session).create_credential(
            CredentialCreate(
                name="server-password",
                auth_type="password",
                username="deployer",
                password="ssh-secret",
            ),
            admin.id,
        )
        session.commit()

    transport = httpx.ASGITransport(app=app_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, app_main.app, credential.id
