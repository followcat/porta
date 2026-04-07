from __future__ import annotations

from app.core.enums import AuthType
from app.services.credential_service import DecryptedCredential
from app.services.ssh_command_builder import SSHCommandBuilder


def test_password_command_uses_sshpass(monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/usr/bin/ssh")
    monkeypatch.setenv("SSHPASS_BIN", "/usr/bin/sshpass")
    builder = SSHCommandBuilder()
    credential = DecryptedCredential(
        id=1,
        name="pw",
        auth_type=AuthType.PASSWORD,
        username="alice",
        password="top-secret",
    )

    command = builder.build(
        ssh_host="example.com",
        ssh_port=2222,
        bind_address="127.0.0.1",
        local_port=9000,
        remote_host="127.0.0.1",
        remote_port=5432,
        strict_host_key_checking=True,
        allow_gateway_ports=False,
        credential=credential,
    )

    assert command.argv[:2] == ["/usr/bin/sshpass", "-e"]
    assert command.env["SSHPASS"] == "top-secret"
    assert "top-secret" not in command.masked_command
    assert "ConnectTimeout=10" in command.argv
    assert "CheckHostIP=no" in command.argv
    assert "StrictHostKeyChecking=yes" in command.argv
    assert "UserKnownHostsFile=" in " ".join(command.argv)
    assert "PreferredAuthentications=password,keyboard-interactive" in command.argv
    assert "PubkeyAuthentication=no" in command.argv
    assert "NumberOfPasswordPrompts=1" in command.argv


def test_key_command_masks_identity_path(monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/usr/bin/ssh")
    builder = SSHCommandBuilder()
    credential = DecryptedCredential(
        id=1,
        name="key",
        auth_type=AuthType.KEY,
        username="alice",
        private_key="irrelevant",
        passphrase="passphrase",
    )

    command = builder.build(
        ssh_host="example.com",
        ssh_port=22,
        bind_address="127.0.0.1",
        local_port=9001,
        remote_host="10.0.0.8",
        remote_port=80,
        strict_host_key_checking=False,
        allow_gateway_ports=True,
        credential=credential,
        identity_file="/tmp/porta_key_secret.pem",
    )

    assert command.argv[:4] == ["/usr/bin/sshpass", "-e", "-P", "Enter passphrase"]
    assert command.env["SSHPASS"] == "passphrase"
    assert "/tmp/porta_key_secret.pem" not in command.masked_command
    assert "porta_key_secret.pem" in command.masked_command
    assert "ConnectTimeout=10" in command.argv
    assert "CheckHostIP=no" in command.argv
    assert "StrictHostKeyChecking=no" in command.argv
    assert "IdentitiesOnly=yes" in command.argv


def test_password_command_falls_back_to_path_when_configured_path_is_wrong(monkeypatch):
    monkeypatch.setenv("SSH_BIN", "/usr/bin/ssh")
    monkeypatch.setenv("SSHPASS_BIN", "/opt/missing/sshpass")
    builder = SSHCommandBuilder()
    credential = DecryptedCredential(
        id=1,
        name="pw",
        auth_type=AuthType.PASSWORD,
        username="alice",
        password="top-secret",
    )

    import app.services.ssh_command_builder as module

    original_resolve = module.resolve_executable

    def fake_resolve(configured_path: str, fallback_name: str) -> str | None:
        if fallback_name == "sshpass":
            return "/usr/bin/sshpass"
        return original_resolve(configured_path, fallback_name)

    monkeypatch.setattr(module, "resolve_executable", fake_resolve)

    command = builder.build(
        ssh_host="example.com",
        ssh_port=2222,
        bind_address="127.0.0.1",
        local_port=9000,
        remote_host="127.0.0.1",
        remote_port=5432,
        strict_host_key_checking=True,
        allow_gateway_ports=False,
        credential=credential,
    )

    assert command.argv[0] == "/usr/bin/sshpass"
