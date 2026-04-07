from __future__ import annotations

import pytest

from app.core.exceptions import CredentialDecryptionError
from app.core.config import get_settings
from app.core.security import decrypt_value, encrypt_value, hash_password, verify_password


def test_encrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("PORTA_MASTER_KEY", "security-test-key")
    payload = encrypt_value("super-secret")
    assert decrypt_value(payload) == "super-secret"


def test_encrypt_uses_random_nonce(monkeypatch):
    monkeypatch.setenv("PORTA_MASTER_KEY", "security-test-key")
    first = encrypt_value("same-value")
    second = encrypt_value("same-value")
    assert first.ciphertext != second.ciphertext
    assert first.nonce != second.nonce


def test_decrypt_with_wrong_key_fails(monkeypatch):
    monkeypatch.setenv("PORTA_MASTER_KEY", "right-key")
    payload = encrypt_value("rotate-me")
    monkeypatch.setenv("PORTA_MASTER_KEY", "wrong-key")
    get_settings.cache_clear()
    with pytest.raises(CredentialDecryptionError):
        decrypt_value(payload)


def test_password_hash_and_verify():
    password_hash = hash_password("hello-world")
    assert verify_password("hello-world", password_hash) is True
    assert verify_password("not-it", password_hash) is False
