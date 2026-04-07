from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings
from app.core.exceptions import CredentialDecryptionError

PBKDF2_ITERATIONS = 600_000
NONCE_SIZE = 12
TAG_SIZE = 16
SALT_SIZE = 16


@dataclass
class EncryptedPayload:
    ciphertext: bytes
    nonce: bytes
    tag: bytes
    key_version: str


def _decode_master_key(raw: str) -> bytes:
    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def get_master_key() -> tuple[bytes, str]:
    settings = get_settings()
    return _decode_master_key(settings.porta_master_key), settings.porta_master_key_version


def encrypt_value(plaintext: str) -> EncryptedPayload:
    key, key_version = get_master_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    encrypted = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return EncryptedPayload(
        ciphertext=encrypted[:-TAG_SIZE],
        nonce=nonce,
        tag=encrypted[-TAG_SIZE:],
        key_version=key_version,
    )


def decrypt_value(payload: EncryptedPayload) -> str:
    key, _ = get_master_key()
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(
            payload.nonce,
            payload.ciphertext + payload.tag,
            None,
        )
    except Exception as exc:  # pragma: no cover - cryptography raises opaque variants
        raise CredentialDecryptionError("failed to decrypt credential") from exc
    return plaintext.decode("utf-8")


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_SIZE)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("utf-8"),
        base64.urlsafe_b64encode(digest).decode("utf-8"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iteration_text, salt_b64, digest_b64 = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
    expected = base64.urlsafe_b64decode(digest_b64.encode("utf-8"))
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        int(iteration_text),
    )
    return hmac.compare_digest(actual, expected)
