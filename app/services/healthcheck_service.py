from __future__ import annotations

import asyncio
from time import perf_counter

import httpx
from pydantic import BaseModel


class HealthcheckResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None = None


class HealthcheckService:
    async def tcp_check(self, host: str, port: int, timeout_ms: int) -> HealthcheckResult:
        start = perf_counter()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host=host, port=port),
                timeout=timeout_ms / 1000,
            )
            writer.close()
            await writer.wait_closed()
            del reader
        except Exception as exc:
            return HealthcheckResult(ok=False, message=str(exc), latency_ms=None)
        latency_ms = int((perf_counter() - start) * 1000)
        return HealthcheckResult(ok=True, message="tcp connect ok", latency_ms=latency_ms)

    async def http_check(self, url: str, timeout_ms: int) -> HealthcheckResult:
        start = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:
            return HealthcheckResult(ok=False, message=str(exc), latency_ms=None)
        latency_ms = int((perf_counter() - start) * 1000)
        return HealthcheckResult(ok=True, message=f"http {response.status_code}", latency_ms=latency_ms)
