from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class ManagedProcess:
    process: asyncio.subprocess.Process
    temp_key_path: str | None = None


class ProcessRegistry:
    def __init__(self) -> None:
        self._items: dict[int, ManagedProcess] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def get(self, tunnel_id: int) -> ManagedProcess | None:
        return self._items.get(tunnel_id)

    def set(self, tunnel_id: int, managed: ManagedProcess) -> None:
        self._items[tunnel_id] = managed

    def remove(self, tunnel_id: int) -> ManagedProcess | None:
        return self._items.pop(tunnel_id, None)

    def lock_for(self, tunnel_id: int) -> asyncio.Lock:
        lock = self._locks.get(tunnel_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[tunnel_id] = lock
        return lock

    async def terminate_all(self, timeout_seconds: float = 5.0) -> None:
        items = list(self._items.items())
        for tunnel_id, managed in items:
            process = managed.process
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            self.remove(tunnel_id)
