"""Encryption for stored credentials (ChatGPT sign-in tokens, API keys).

The key comes from BHASHA_SECRET_KEY. Changing or losing it makes stored
sign-ins unreadable; you then sign in again. Nothing else depends on it."""

import base64
import hashlib
import hmac
import uuid

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretKeyMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("BHASHA_SECRET_KEY is not set; add it to .env (openssl rand -hex 32)")


class UnreadableSecretError(RuntimeError):
    pass


def _secret() -> str:
    secret = get_settings().secret_key
    if not secret:
        raise SecretKeyMissingError
    return secret


def _fernet() -> Fernet:
    key = hashlib.sha256(b"bhasha-fernet:" + _secret().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as error:
        raise UnreadableSecretError("stored credential cannot be read with this BHASHA_SECRET_KEY") from error


def install_uuid(purpose: str) -> str:
    """A stable per-install identifier for `purpose`, derived from the secret."""
    raw = hmac.new(_secret().encode(), purpose.encode(), hashlib.sha256).digest()[:16]
    return f"urn:uuid:{uuid.UUID(bytes=raw, version=4)}"
