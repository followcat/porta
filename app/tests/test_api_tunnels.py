from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import auth as auth_routes
from app.api.routes import tunnels as tunnel_routes
from app.schemas.auth import LoginRequest
from app.schemas.credential import CredentialCreate
from app.schemas.tunnel import TunnelCreate
from app.services.auth_service import AuthService
from app.services.credential_service import CredentialService


@pytest.mark.asyncio
async def test_tunnel_crud_and_lifecycle(session_factory):
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

        request = SimpleNamespace(session={})
        login = auth_routes.login(LoginRequest(username="admin", password="secret-password"), request, session)
        assert login["status"] == "ok"
        assert request.session["user_id"] == admin.id

        created = tunnel_routes.create_tunnel(
            TunnelCreate(
                name="reporting",
                description="reporting tunnel",
                ssh_host="example.com",
                ssh_port=22,
                credential_id=credential.id,
                bind_address="127.0.0.1",
                local_port=18090,
                remote_host="127.0.0.1",
                remote_port=8090,
                group_name="reports",
                tags=["reporting"],
                desired_state="stopped",
                healthcheck_type="tcp",
            ),
            session,
            admin,
        )
        assert created.name == "reporting"

        listing = tunnel_routes.list_tunnels(
            group_name=None,
            actual_state=None,
            desired_state=None,
            enabled=None,
            keyword=None,
            db=session,
            _=admin,
        )
        assert any(item.id == created.id for item in listing)

        manager = SimpleNamespace(run_once=AsyncMock())
        stop = await tunnel_routes.stop_tunnel(created.id, session, admin, manager)
        assert stop["status"] == "ok"
        manager.run_once.assert_awaited()

        manager.run_once.reset_mock()
        start = await tunnel_routes.start_tunnel(created.id, session, admin, manager)
        assert start["status"] == "ok"
        manager.run_once.assert_awaited()

        detail = tunnel_routes.get_tunnel(created.id, session, admin)
        assert detail.tunnel.name == "reporting"


@pytest.mark.asyncio
async def test_shared_access_auto_enables_gateway_ports(session_factory):
    with session_factory() as session:
        admin = AuthService(session).create_admin("admin", "secret-password")
        credential = CredentialService(session).create_credential(
            CredentialCreate(
                name="shared-password",
                auth_type="password",
                username="deployer",
                password="ssh-secret",
            ),
            admin.id,
        )
        session.commit()

        created = tunnel_routes.create_tunnel(
            TunnelCreate(
                name="shared-reporting",
                ssh_host="example.com",
                ssh_port=22,
                credential_id=credential.id,
                bind_address="0.0.0.0",
                local_port=18091,
                remote_host="127.0.0.1",
                remote_port=8091,
                group_name="reports",
                tags=["shared"],
                desired_state="stopped",
                healthcheck_type="tcp",
                allow_gateway_ports=False,
            ),
            session,
            admin,
        )

        assert created.bind_address == "0.0.0.0"
        assert created.allow_gateway_ports is True
