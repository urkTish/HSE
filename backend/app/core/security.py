"""Password hashing and policy, JWT and one-time tokens (spec §5.1)."""

import hashlib
import secrets
import uuid
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.clock import now
from app.core.config import get_settings


@lru_cache
def _hasher() -> PasswordHasher:
    if get_settings().environment == "test":
        return PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    return PasswordHasher()  # Argon2id defaults


def hash_password(password: str) -> str:
    return _hasher().hash(password)


@lru_cache
def _dummy_hash() -> str:
    return hash_password("dummy-password-for-timing-equalisation")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time: always runs one Argon2 verification."""
    try:
        return _hasher().verify(password_hash or _dummy_hash(), password) and bool(password_hash)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def _breached() -> frozenset[str]:
    text = resources.files("app.data").joinpath("common_passwords.txt").read_text("utf-8")
    return frozenset(line.strip().casefold() for line in text.splitlines() if line.strip())


def password_problems(password: str, email: str) -> list[str]:
    """Returns English problems; empty list = acceptable (rule 2)."""
    problems: list[str] = []
    if len(password) < 12:
        problems.append("must be at least 12 characters")
    classes = sum(
        [
            any(c.isupper() for c in password),
            any(c.islower() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        problems.append("must contain at least 3 of: upper case, lower case, digit, symbol")
    if password.casefold() == email.split("@", maxsplit=1)[0].casefold():
        problems.append("must not equal the email name")
    if password.casefold() in _breached():
        problems.append("is too common (found in breached-password list)")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def encode_jwt(user_id: uuid.UUID, session_id: uuid.UUID, expires_at: datetime) -> str:
    s = get_settings()
    payload = {"sub": str(user_id), "sid": str(session_id), "exp": expires_at}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def encode_gate_jwt(device_pk: uuid.UUID, session_id: uuid.UUID, expires_at: datetime) -> str:
    """Gate-device session token (spec 2-access-permits GC-1); `typ = gate`."""
    s = get_settings()
    payload = {"sub": str(device_pk), "sid": str(session_id), "typ": "gate", "exp": expires_at}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_jwt(token: str) -> dict[str, Any] | None:
    """Expiry is checked against `app.core.clock.now()` (so a pinned clock applies)."""
    s = get_settings()
    try:
        data: dict[str, Any] = jwt.decode(
            token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"verify_exp": False}
        )
    except jwt.PyJWTError:
        return None
    exp = data.get("exp")
    if exp is not None and (not isinstance(exp, int | float) or exp <= now().timestamp()):
        return None
    return data
