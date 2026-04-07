from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class Tunnel(Base):
    __tablename__ = "tunnels"
    __table_args__ = (
        UniqueConstraint("bind_address", "local_port", name="uk_bind_local_port"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ssh_host: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id"), nullable=False)

    bind_address: Mapped[str] = mapped_column(String(64), nullable=False, default="127.0.0.1")
    local_port: Mapped[int] = mapped_column(Integer, nullable=False)
    remote_host: Mapped[str] = mapped_column(String(255), nullable=False)
    remote_port: Mapped[int] = mapped_column(Integer, nullable=False)

    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    auto_start: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    desired_state: Mapped[str] = mapped_column(String(32), nullable=False, default="running")

    restart_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="always")
    restart_backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_restart_backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    max_retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    check_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    healthcheck_type: Mapped[str] = mapped_column(String(32), nullable=False, default="tcp")
    healthcheck_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    healthcheck_timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)
    healthcheck_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    strict_host_key_checking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_gateway_ports: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    credential = relationship("Credential")
    runtime = relationship("TunnelRuntime", back_populates="tunnel", uselist=False)
