from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SupervisorManager:
    def __init__(
        self,
        enabled_tunnel_ids_provider: Callable[[], list[int]],
        worker_factory: Callable[[int], object],
    ) -> None:
        self.settings = get_settings()
        self.enabled_tunnel_ids_provider = enabled_tunnel_ids_provider
        self.worker_factory = worker_factory
        self._running = False

    async def run_once(self, tunnel_ids: Iterable[int] | None = None) -> None:
        if tunnel_ids is None:
            ids = self.enabled_tunnel_ids_provider()
        else:
            ids = list(tunnel_ids)
        for tunnel_id in ids:
            worker = self.worker_factory(tunnel_id)
            try:
                await worker.reconcile()
            except Exception:
                logger.exception("supervisor reconcile failed for tunnel_id=%s", tunnel_id)

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            await self.run_once()
            await asyncio.sleep(self.settings.supervisor_loop_seconds)

    def stop(self) -> None:
        self._running = False
