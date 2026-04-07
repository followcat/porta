from __future__ import annotations

import asyncio
import socket


class PortProbeService:
    def local_check_host(self, host: str) -> str:
        if host in {"0.0.0.0", "::", "*", ""}:
            return "127.0.0.1"
        return host

    def is_bind_available(self, host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return False
        return True

    async def can_connect(self, host: str, port: int, timeout_ms: int = 1000) -> bool:
        host = self.local_check_host(host)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host=host, port=port),
                timeout=timeout_ms / 1000,
            )
            writer.close()
            await writer.wait_closed()
            del reader
            return True
        except Exception:
            return False
