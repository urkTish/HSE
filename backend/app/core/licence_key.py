"""Licence key format: Ed25519-signed terms (trial readiness, package B, D-289).

A key is one line of text: ``HSE1.<payload>.<signature>``, both parts base64url without padding.
The payload is UTF-8 JSON with the terms; the signature is Ed25519 over the payload bytes exactly
as sent. The public key ships with the app (``app/data/licence_public_key.pem``, or the
``LICENCE_PUBLIC_KEY`` setting); the private key stays with the vendor (``app.licence_cli``).

No database access here, so the CLI and the tests can use it on their own.
"""

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PREFIX = "HSE1"
FORMAT_VERSION = 1
BUNDLES = ("trial", "basic", "professional", "enterprise")
LIMIT_FIELDS = ("max_projects", "max_users", "max_storage_gb", "ai_questions_per_month")
PUBLIC_KEY_FILE = Path(__file__).resolve().parents[1] / "data" / "licence_public_key.pem"


class LicenceKeyError(ValueError):
    """The key cannot be trusted. ``reason`` is a stable machine word for the UI and logs."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class LicenceTerms:
    """What a signed key grants. ``None`` limits are unlimited. Fields beyond these (for later
    bundle-based module gating) stay readable in ``extra``."""

    licence_id: str
    customer: str
    bundle: str
    issued_on: date
    valid_until: date
    max_projects: int | None
    max_users: int | None
    max_storage_gb: int | None
    ai_questions_per_month: int | None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_trial(self) -> bool:
        return self.bundle == "trial"

    def to_payload(self) -> dict[str, Any]:
        return {
            "v": FORMAT_VERSION,
            "id": self.licence_id,
            "customer": self.customer,
            "bundle": self.bundle,
            "issued_on": self.issued_on.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            **{f: getattr(self, f) for f in LIMIT_FIELDS},
            **self.extra,
        }


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def normalise(key: str) -> str:
    """Keys pasted from e-mail may carry line breaks or spaces; none belong to the format."""
    return "".join(key.split())


# ---- keys ---------------------------------------------------------------------------------------


def load_public_key(text: str) -> Ed25519PublicKey:
    """PEM (``-----BEGIN PUBLIC KEY-----``) or base64 of the 32 raw bytes."""
    text = text.strip()
    if text.startswith("-----BEGIN"):
        key = serialization.load_pem_public_key(text.encode("ascii"))
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("The public key is not an Ed25519 key.")
        return key
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(text))


def shipped_public_key(override: str | None = None) -> Ed25519PublicKey | None:
    """The configured public key: the override (setting) first, else the shipped file."""
    if override and override.strip():
        return load_public_key(override)
    if PUBLIC_KEY_FILE.is_file():
        text = PUBLIC_KEY_FILE.read_text(encoding="ascii").strip()
        return load_public_key(text) if text else None
    return None


def public_pem(key: Ed25519PublicKey) -> str:
    return key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def private_pem(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def load_private_key(pem: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The private key is not an Ed25519 key.")
    return key


# ---- sign / verify ------------------------------------------------------------------------------


def sign(terms: LicenceTerms, private_key: Ed25519PrivateKey) -> str:
    payload = json.dumps(terms.to_payload(), ensure_ascii=False, separators=(",", ":")).encode()
    return f"{PREFIX}.{_b64e(payload)}.{_b64e(private_key.sign(payload))}"


def _limit(data: dict[str, Any], name: str) -> int | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LicenceKeyError("malformed", f"{name} must be a whole number of 0 or more.")
    return value


def parse_terms(data: dict[str, Any]) -> LicenceTerms:
    if data.get("v") != FORMAT_VERSION:
        raise LicenceKeyError("unsupported_version", "This key format is not supported.")
    try:
        issued = date.fromisoformat(str(data["issued_on"]))
        until = date.fromisoformat(str(data["valid_until"]))
        licence_id = str(data["id"]).strip()
        customer = str(data["customer"]).strip()
        bundle = str(data["bundle"])
    except (KeyError, ValueError) as exc:
        raise LicenceKeyError("malformed", "The key is missing a field or a date.") from exc
    if bundle not in BUNDLES:
        raise LicenceKeyError("malformed", f"Unknown bundle {bundle!r}.")
    if not licence_id or not customer or until < issued:
        raise LicenceKeyError("malformed", "The key has an empty name or impossible dates.")
    known = {"v", "id", "customer", "bundle", "issued_on", "valid_until", *LIMIT_FIELDS}
    return LicenceTerms(
        licence_id=licence_id[:80],
        customer=customer[:200],
        bundle=bundle,
        issued_on=issued,
        valid_until=until,
        **{f: _limit(data, f) for f in LIMIT_FIELDS},
        extra={k: v for k, v in data.items() if k not in known},
    )


def verify(key: str, public_key: Ed25519PublicKey | None) -> LicenceTerms:
    """Check the signature and read the terms. Raises LicenceKeyError; never checks dates
    against today (the caller decides what an expired key means)."""
    if public_key is None:
        raise LicenceKeyError(
            "no_public_key", "This install has no licence public key, so no key can be checked."
        )
    parts = normalise(key).split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise LicenceKeyError("malformed", "This is not a licence key (expected HSE1.…).")
    try:
        payload = _b64d(parts[1])
        signature = _b64d(parts[2])
    except (binascii.Error, ValueError) as exc:
        raise LicenceKeyError("malformed", "The key text is damaged.") from exc
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise LicenceKeyError(
            "bad_signature", "The key signature does not match (altered or not ours)."
        ) from exc
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenceKeyError("malformed", "The key content cannot be read.") from exc
    if not isinstance(data, dict):
        raise LicenceKeyError("malformed", "The key content cannot be read.")
    return parse_terms(data)
