from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import shutil

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Porta"
    env: str = "dev"
    debug: bool = False

    secret_key: str = Field(default="change-me")
    porta_master_key: str = Field(default="change-me-too")
    porta_master_key_version: str = "v1"

    mysql_dsn: str = Field(
        default="mysql+pymysql://porta:porta@127.0.0.1:3306/porta?charset=utf8mb4"
    )

    ssh_bin: str = "/usr/bin/ssh"
    sshpass_bin: str = "/usr/bin/sshpass"
    ssh_keyscan_bin: str = "/usr/bin/ssh-keyscan"
    ssh_known_hosts_file: str = "~/.ssh/known_hosts"
    supervisor_loop_seconds: int = 3
    tunnel_startup_grace_seconds: int = 2
    session_cookie_name: str = "porta_session"
    auto_create_tables: bool = False

    template_dir: Path = Path("app/web/templates")
    static_dir: Path = Path("app/web/static")

    @property
    def database_url(self) -> str:
        return self.mysql_dsn


def resolve_executable(configured_path: str, fallback_name: str) -> str | None:
    candidate = configured_path.strip()
    if candidate:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
        resolved_candidate = shutil.which(candidate)
        if resolved_candidate:
            return resolved_candidate
        basename = Path(candidate).name
        if basename:
            resolved_basename = shutil.which(basename)
            if resolved_basename:
                return resolved_basename

    return shutil.which(fallback_name)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
