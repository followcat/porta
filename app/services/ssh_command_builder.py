from __future__ import annotations

import shlex
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_settings, resolve_executable
from app.core.enums import AuthType
from app.services.credential_service import DecryptedCredential


class SSHCommandParts(BaseModel):
    argv: list[str]
    env: dict[str, str]
    masked_command: str


class SSHCommandBuilder:
    def __init__(self) -> None:
        self.settings = get_settings()

    def build(
        self,
        *,
        ssh_host: str,
        ssh_port: int,
        bind_address: str,
        local_port: int,
        remote_host: str,
        remote_port: int,
        strict_host_key_checking: bool,
        allow_gateway_ports: bool,
        credential: DecryptedCredential,
        identity_file: str | None = None,
    ) -> SSHCommandParts:
        ssh_bin = resolve_executable(self.settings.ssh_bin, "ssh") or self.settings.ssh_bin
        sshpass_bin = resolve_executable(self.settings.sshpass_bin, "sshpass") or self.settings.sshpass_bin

        ssh_argv = [
            ssh_bin,
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "TCPKeepAlive=yes",
            "-o",
            f"StrictHostKeyChecking={'yes' if strict_host_key_checking else 'no'}",
            "-L",
            f"{bind_address}:{local_port}:{remote_host}:{remote_port}",
            "-p",
            str(ssh_port),
        ]
        if allow_gateway_ports:
            ssh_argv.append("-g")
        if identity_file:
            ssh_argv.extend(["-i", identity_file])
            ssh_argv.extend(["-o", "IdentitiesOnly=yes"])
        ssh_argv.append(f"{credential.username}@{ssh_host}")

        argv = list(ssh_argv)
        env: dict[str, str] = {}
        if credential.auth_type == AuthType.PASSWORD and credential.password:
            password_argv = [
                "-o",
                "PreferredAuthentications=password,keyboard-interactive",
                "-o",
                "PubkeyAuthentication=no",
                "-o",
                "NumberOfPasswordPrompts=1",
            ]
            argv = [sshpass_bin, "-e"] + ssh_argv[:-1] + password_argv + [ssh_argv[-1]]
            env["SSHPASS"] = credential.password
        elif credential.auth_type == AuthType.KEY and credential.passphrase:
            argv = [sshpass_bin, "-e", "-P", "Enter passphrase"] + ssh_argv
            env["SSHPASS"] = credential.passphrase

        masked = list(argv)
        if identity_file:
            index = masked.index(identity_file)
            masked[index] = Path(identity_file).name
        masked_command = shlex.join(masked)
        return SSHCommandParts(argv=argv, env=env, masked_command=masked_command)
