from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)

    password_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary(4096), nullable=True)
    password_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(64), nullable=True)
    password_tag: Mapped[bytes | None] = mapped_column(LargeBinary(64), nullable=True)

    private_key_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    private_key_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(64), nullable=True)
    private_key_tag: Mapped[bytes | None] = mapped_column(LargeBinary(64), nullable=True)

    passphrase_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary(4096), nullable=True)
    passphrase_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(64), nullable=True)
    passphrase_tag: Mapped[bytes | None] = mapped_column(LargeBinary(64), nullable=True)

    key_version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
