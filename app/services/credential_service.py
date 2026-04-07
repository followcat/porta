from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import AuthType
from app.core.exceptions import ResourceConflictError, ValidationError
from app.core.security import EncryptedPayload, decrypt_value, encrypt_value
from app.db.models.credential import Credential
from app.repositories.credential_repo import CredentialRepository
from app.schemas.credential import CredentialCreate, CredentialRead, CredentialUpdate
from app.services.audit_service import AuditService


@dataclass
class DecryptedCredential:
    id: int
    name: str
    auth_type: AuthType
    username: str
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None


class CredentialService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = CredentialRepository(session)
        self.audit = AuditService(session)

    def list_credentials(self) -> list[CredentialRead]:
        items: list[CredentialRead] = []
        for credential in self.repo.list():
            item = CredentialRead.model_validate(credential)
            items.append(item.model_copy(update={"in_use": self.repo.usage_count(credential.id)}))
        return items

    def get_credential(self, credential_id: int) -> Credential:
        credential = self.repo.get(credential_id)
        if not credential:
            raise ValidationError("credential not found")
        return credential

    def create_credential(self, data: CredentialCreate, actor_id: int | None) -> Credential:
        self._validate_secret_inputs(data.auth_type, data.password, data.private_key, creating=True)
        if self.repo.get_by_name(data.name):
            raise ResourceConflictError("credential name already exists")
        credential = Credential(
            name=data.name,
            auth_type=data.auth_type.value,
            username=data.username,
            description=data.description,
            created_by=actor_id,
            updated_by=actor_id,
            key_version="v1",
        )
        self._apply_secrets(credential, data.password, data.private_key, data.passphrase)
        self.repo.create(credential)
        self.audit.log(actor_id, "credential_created", "credential", str(credential.id), {"name": credential.name})
        return credential

    def update_credential(self, credential_id: int, data: CredentialUpdate, actor_id: int | None) -> Credential:
        credential = self.get_credential(credential_id)
        existing_by_name = self.repo.get_by_name(data.name)
        if existing_by_name and existing_by_name.id != credential.id:
            raise ResourceConflictError("credential name already exists")
        self._validate_secret_inputs(data.auth_type, data.password, data.private_key, creating=False, credential=credential)

        credential.name = data.name
        credential.auth_type = data.auth_type.value
        credential.username = data.username
        credential.description = data.description
        credential.updated_by = actor_id
        self._apply_secrets(
            credential,
            data.password,
            data.private_key,
            data.passphrase,
            keep_existing=True,
        )
        self.audit.log(actor_id, "credential_updated", "credential", str(credential.id), {"name": credential.name})
        return credential

    def delete_credential(self, credential_id: int, actor_id: int | None) -> None:
        credential = self.get_credential(credential_id)
        if self.repo.usage_count(credential.id) > 0:
            raise ValidationError("credential is still referenced by tunnels")
        self.repo.delete(credential)
        self.audit.log(actor_id, "credential_deleted", "credential", str(credential.id), {"name": credential.name})

    def decrypt_credential(self, credential: Credential) -> DecryptedCredential:
        return DecryptedCredential(
            id=credential.id,
            name=credential.name,
            auth_type=AuthType(credential.auth_type),
            username=credential.username,
            password=self._decrypt_payload(
                credential.password_ciphertext,
                credential.password_nonce,
                credential.password_tag,
                credential.key_version,
            ),
            private_key=self._decrypt_payload(
                credential.private_key_ciphertext,
                credential.private_key_nonce,
                credential.private_key_tag,
                credential.key_version,
            ),
            passphrase=self._decrypt_payload(
                credential.passphrase_ciphertext,
                credential.passphrase_nonce,
                credential.passphrase_tag,
                credential.key_version,
            ),
        )

    def write_private_key_tempfile(self, credential: DecryptedCredential) -> str:
        if not credential.private_key:
            raise ValidationError("private key is required for key auth")
        handle = tempfile.NamedTemporaryFile("w", delete=False, prefix="porta_key_", suffix=".pem")
        try:
            handle.write(credential.private_key)
            handle.flush()
        finally:
            handle.close()
        os.chmod(handle.name, 0o600)
        return handle.name

    def _validate_secret_inputs(
        self,
        auth_type: AuthType,
        password: str | None,
        private_key: str | None,
        *,
        creating: bool,
        credential: Credential | None = None,
    ) -> None:
        if auth_type == AuthType.PASSWORD:
            has_secret = bool(password) or (credential is not None and credential.password_ciphertext)
            if creating and not password:
                raise ValidationError("password auth requires password")
            if not creating and not has_secret:
                raise ValidationError("password auth requires password")
        if auth_type == AuthType.KEY:
            has_secret = bool(private_key) or (credential is not None and credential.private_key_ciphertext)
            if creating and not private_key:
                raise ValidationError("key auth requires private key")
            if not creating and not has_secret:
                raise ValidationError("key auth requires private key")

    def _decrypt_payload(
        self,
        ciphertext: bytes | None,
        nonce: bytes | None,
        tag: bytes | None,
        key_version: str,
    ) -> str | None:
        if not ciphertext or not nonce or not tag:
            return None
        payload = EncryptedPayload(ciphertext=ciphertext, nonce=nonce, tag=tag, key_version=key_version)
        return decrypt_value(payload)

    def _apply_secrets(
        self,
        credential: Credential,
        password: str | None,
        private_key: str | None,
        passphrase: str | None,
        *,
        keep_existing: bool = False,
    ) -> None:
        if password or not keep_existing:
            self._store_encrypted_field(credential, "password", password)
        if private_key or not keep_existing:
            self._store_encrypted_field(credential, "private_key", private_key)
        if passphrase or not keep_existing:
            self._store_encrypted_field(credential, "passphrase", passphrase)

    def _store_encrypted_field(self, credential: Credential, prefix: str, value: str | None) -> None:
        if not value:
            setattr(credential, f"{prefix}_ciphertext", None)
            setattr(credential, f"{prefix}_nonce", None)
            setattr(credential, f"{prefix}_tag", None)
            return
        encrypted = encrypt_value(value)
        setattr(credential, f"{prefix}_ciphertext", encrypted.ciphertext)
        setattr(credential, f"{prefix}_nonce", encrypted.nonce)
        setattr(credential, f"{prefix}_tag", encrypted.tag)
        credential.key_version = encrypted.key_version
