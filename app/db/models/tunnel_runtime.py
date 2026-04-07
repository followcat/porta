from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class TunnelRuntime(Base):
    __tablename__ = "tunnel_runtime"

    tunnel_id: Mapped[int] = mapped_column(ForeignKey("tunnels.id", ondelete="CASCADE"), primary_key=True)
    actual_state: Mapped[str] = mapped_column(Text, nullable=False, default="stopped")
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    command_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_exit_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    restart_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    local_bind_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    healthcheck_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_healthcheck_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_healthcheck_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    current_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    tunnel = relationship("Tunnel", back_populates="runtime")
