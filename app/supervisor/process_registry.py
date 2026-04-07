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

    def get(self, tunnel_id: int) -> ManagedProcess | None:
        return self._items.get(tunnel_id)

    def set(self, tunnel_id: int, managed: ManagedProcess) -> None:
        self._items[tunnel_id] = managed

    def remove(self, tunnel_id: int) -> ManagedProcess | None:
        return self._items.pop(tunnel_id, None)
