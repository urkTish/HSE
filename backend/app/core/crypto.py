"""Field-level encryption for ID numbers (spec 1-dashboard P2) and signed URLs (P1-3)."""

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def _key() -> bytes:
    return hashlib.sha256(get_settings().field_encryption_key.encode()).digest()


def encrypt(value: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, value.encode(), b"hse-field")


def decrypt(blob: bytes) -> str:
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], b"hse-field").decode()


def encrypt_bytes(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, data, b"hse-file")


def decrypt_bytes(blob: bytes) -> bytes:
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], b"hse-file")


def mask_id(value: str) -> str:
    """`2000000017` → `2*******17` (first char, last two)."""
    if len(value) <= 3:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 3) + value[-2:]


def sign(message: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def verify(message: str, signature: str, secret: str) -> bool:
    return hmac.compare_digest(sign(message, secret), signature)
