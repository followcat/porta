from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings, resolve_executable
from app.core.exceptions import DependencyMissingError, ValidationError


@dataclass
class KnownHostResult:
    added: bool
    known_hosts_path: str
    entries_added: int


class SSHKnownHostsService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def known_hosts_path(self) -> Path:
        return Path(os.path.expanduser(self.settings.ssh_known_hosts_file))

    async def ensure_known_host(self, host: str, port: int) -> KnownHostResult:
        keyscan_bin = resolve_executable(self.settings.ssh_keyscan_bin, "ssh-keyscan")
        if not keyscan_bin:
            raise DependencyMissingError("ssh-keyscan executable not found")

        path = self.known_hosts_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        os.chmod(path.parent, 0o700)
        os.chmod(path, 0o600)

        proc = await asyncio.create_subprocess_exec(
            keyscan_bin,
            "-p",
            str(port),
            host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="ignore")
        error_output = stderr.decode("utf-8", errors="ignore").strip()

        scanned_lines = [
            line.strip()
            for line in output.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if proc.returncode != 0 or not scanned_lines:
            message = error_output or f"ssh-keyscan returned no host keys for {host}:{port}"
            raise ValidationError(message)

        existing_entries = {
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip()
        }
        new_entries = [line for line in scanned_lines if line not in existing_entries]

        if new_entries:
            with path.open("a", encoding="utf-8") as handle:
                if path.stat().st_size > 0:
                    handle.write("\n")
                handle.write("\n".join(new_entries))
                handle.write("\n")

        return KnownHostResult(
            added=bool(new_entries),
            known_hosts_path=str(path),
            entries_added=len(new_entries),
        )
