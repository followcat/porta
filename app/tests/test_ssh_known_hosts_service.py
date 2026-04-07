from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ssh_known_hosts_service import SSHKnownHostsService


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


async def _fake_subprocess_success(*args, **kwargs):
    del args, kwargs
    return FakeProcess(b"[example.com]:3008 ssh-ed25519 AAAATESTKEY")


@pytest.mark.asyncio
async def test_known_hosts_service_adds_scanned_entry(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SSH_KEYSCAN_BIN", "/usr/bin/ssh-keyscan")
    monkeypatch.setenv("SSH_KNOWN_HOSTS_FILE", str(tmp_path / "known_hosts"))

    import app.services.ssh_known_hosts_service as module

    monkeypatch.setattr(module, "resolve_executable", lambda configured_path, fallback_name: "/usr/bin/ssh-keyscan")
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", _fake_subprocess_success)

    service = SSHKnownHostsService()
    result = await service.ensure_known_host("example.com", 3008)

    assert result.added is True
    assert result.entries_added == 1
    assert service.known_hosts_path.read_text(encoding="utf-8").strip() == "[example.com]:3008 ssh-ed25519 AAAATESTKEY"


@pytest.mark.asyncio
async def test_known_hosts_service_deduplicates_entries(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SSH_KEYSCAN_BIN", "/usr/bin/ssh-keyscan")
    monkeypatch.setenv("SSH_KNOWN_HOSTS_FILE", str(tmp_path / "known_hosts"))

    import app.services.ssh_known_hosts_service as module

    monkeypatch.setattr(module, "resolve_executable", lambda configured_path, fallback_name: "/usr/bin/ssh-keyscan")
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", _fake_subprocess_success)

    service = SSHKnownHostsService()
    await service.ensure_known_host("example.com", 3008)
    result = await service.ensure_known_host("example.com", 3008)

    assert result.added is False
    assert result.entries_added == 0
