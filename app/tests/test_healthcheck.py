from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services.healthcheck_service import HealthcheckService


class FakeWriter:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


@pytest.mark.asyncio
async def test_tcp_healthcheck_success(monkeypatch):
    service = HealthcheckService()

    async def fake_open_connection(*args, **kwargs):
        del args, kwargs
        return object(), FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    result = await service.tcp_check("127.0.0.1", 9999, 1000)
    assert result.ok is True
    assert result.latency_ms is not None


@pytest.mark.asyncio
async def test_http_healthcheck_success(monkeypatch):
    service = HealthcheckService()

    async def fake_get(self, url):
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await service.http_check("http://127.0.0.1:9999/healthz", 1000)
    assert result.ok is True
    assert result.message == "http 200"


@pytest.mark.asyncio
async def test_tcp_healthcheck_failure(monkeypatch):
    service = HealthcheckService()

    async def fake_open_connection(*args, **kwargs):
        del args, kwargs
        raise OSError("connect failed")

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    result = await service.tcp_check("127.0.0.1", 65530, 50)
    assert result.ok is False


def test_port_probe_maps_wildcard_bind_to_loopback():
    from app.services.port_probe_service import PortProbeService

    service = PortProbeService()
    assert service.local_check_host("0.0.0.0") == "127.0.0.1"
    assert service.local_check_host("::") == "127.0.0.1"
    assert service.local_check_host("127.0.0.1") == "127.0.0.1"
