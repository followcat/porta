from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.credential import Credential
from app.db.models.tunnel import Tunnel


class CredentialRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Credential]:
        return list(self.session.scalars(select(Credential).order_by(Credential.name)))

    def get(self, credential_id: int) -> Credential | None:
        return self.session.get(Credential, credential_id)

    def get_by_name(self, name: str) -> Credential | None:
        return self.session.scalar(select(Credential).where(Credential.name == name))

    def create(self, credential: Credential) -> Credential:
        self.session.add(credential)
        self.session.flush()
        return credential

    def delete(self, credential: Credential) -> None:
        self.session.delete(credential)

    def usage_count(self, credential_id: int) -> int:
        result = self.session.scalar(
            select(func.count(Tunnel.id)).where(Tunnel.credential_id == credential_id)
        )
        return int(result or 0)
