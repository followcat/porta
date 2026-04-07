from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AuthType


class CredentialCreate(BaseModel):
    name: str
    auth_type: AuthType
    username: str
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None
    description: str | None = None


class CredentialUpdate(BaseModel):
    name: str
    auth_type: AuthType
    username: str
    password: str | None = Field(default=None)
    private_key: str | None = Field(default=None)
    passphrase: str | None = Field(default=None)
    description: str | None = None


class CredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    auth_type: AuthType
    username: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    in_use: int = 0


class CredentialOption(BaseModel):
    id: int
    name: str
    auth_type: AuthType
    username: str
