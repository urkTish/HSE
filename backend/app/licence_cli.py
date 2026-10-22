"""Licence key tool for the vendor (trial readiness, package B; docs/LICENSING.md).

    uv run python -m app.licence_cli keygen
    uv run python -m app.licence_cli issue --customer "ACME Airports" --bundle trial
    uv run python -m app.licence_cli show "HSE1.…"

``keygen`` makes the signing key pair once: the private key goes outside the repository (default
``~/.hse-licence/licence-private.pem``, readable only by you) and the public key into
``app/data/licence_public_key.pem``, which ships with the app (commit it). ``issue`` prints a key
to send to the customer; they paste it on the Licence page. Never commit the private key.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import licence_key as lk

DEFAULT_PRIVATE = Path.home() / ".hse-licence" / "licence-private.pem"

# Bundle defaults from the owner's decisions of 2026-10-21 (handover "Decisions already made").
# None = unlimited. Every value can be overridden on the command line.
BUNDLE_DEFAULTS: dict[str, dict[str, int | None]] = {
    "trial": {
        "days": 30,
        "max_projects": 1,
        "max_users": 50,
        "max_storage_gb": 10,
        "ai_questions_per_month": 100,
    },
    "basic": {
        "days": None,
        "max_projects": 1,
        "max_users": None,
        "max_storage_gb": 50,
        "ai_questions_per_month": 0,
    },
    "professional": {
        "days": None,
        "max_projects": 1,
        "max_users": None,
        "max_storage_gb": 200,
        "ai_questions_per_month": 300,
    },
    "enterprise": {
        "days": None,
        "max_projects": 1,
        "max_users": None,
        "max_storage_gb": 500,
        "ai_questions_per_month": 1000,
    },
}


def _limit(text: str) -> int | None:
    if text.lower() in ("none", "unlimited", "-"):
        return None
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or more (or 'unlimited')")
    return value


def keygen(args: argparse.Namespace) -> int:
    private_path = Path(args.private_out).expanduser()
    public_path = Path(args.public_out).expanduser()
    if private_path.exists() and not args.force:
        print(f"{private_path} already exists; use --force to replace it.", file=sys.stderr)
        print("Replacing it makes every key issued so far invalid.", file=sys.stderr)
        return 1
    key = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(lk.private_pem(key), encoding="ascii")
    os.chmod(private_path, 0o600)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(lk.public_pem(key.public_key()), encoding="ascii")
    print(f"Private key (keep secret, back it up, never commit): {private_path}")
    print(f"Public key (commit it, it ships with the app):     {public_path}")
    return 0


def issue(args: argparse.Namespace) -> int:
    private = lk.load_private_key(Path(args.private_key).expanduser().read_text(encoding="ascii"))
    d = BUNDLE_DEFAULTS[args.bundle]
    issued = date.fromisoformat(args.issued_on) if args.issued_on else date.today()
    if args.valid_until:
        until = date.fromisoformat(args.valid_until)
    elif args.days or d["days"]:
        until = issued + timedelta(days=(args.days or d["days"] or 0) - 1)
    else:
        print("Give --valid-until YYYY-MM-DD or --days N for this bundle.", file=sys.stderr)
        return 2

    def pick(name: str) -> int | None:
        given = getattr(args, name)
        return d[name] if given == "default" else _limit(given)

    terms = lk.LicenceTerms(
        licence_id=args.licence_id or f"LIC-{issued:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}",
        customer=args.customer,
        bundle=args.bundle,
        issued_on=issued,
        valid_until=until,
        max_projects=pick("max_projects"),
        max_users=pick("max_users"),
        max_storage_gb=pick("max_storage_gb"),
        ai_questions_per_month=pick("ai_questions_per_month"),
    )
    key = lk.sign(terms, private)
    lk.verify(key, private.public_key())  # self-check before handing it out
    print(json.dumps(terms.to_payload(), indent=2, ensure_ascii=False), file=sys.stderr)
    print(key)
    return 0


def show(args: argparse.Namespace) -> int:
    pub = (
        lk.load_public_key(Path(args.public_key).read_text(encoding="ascii"))
        if args.public_key
        else lk.shipped_public_key(os.environ.get("LICENCE_PUBLIC_KEY"))
    )
    try:
        terms = lk.verify(args.key, pub)
    except lk.LicenceKeyError as exc:
        print(f"NOT VALID ({exc.reason}): {exc}", file=sys.stderr)
        return 1
    print(json.dumps(terms.to_payload(), indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.licence_cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    k = sub.add_parser("keygen", help="Make the signing key pair (once).")
    k.add_argument("--private-out", default=str(DEFAULT_PRIVATE))
    k.add_argument("--public-out", default=str(lk.PUBLIC_KEY_FILE))
    k.add_argument("--force", action="store_true", help="Replace an existing private key.")
    k.set_defaults(func=keygen)

    i = sub.add_parser("issue", help="Print a signed licence key for a customer.")
    i.add_argument("--private-key", default=str(DEFAULT_PRIVATE))
    i.add_argument("--customer", required=True)
    i.add_argument("--bundle", required=True, choices=lk.BUNDLES)
    i.add_argument("--licence-id", help="Default: LIC-<date>-<random>.")
    i.add_argument("--issued-on", help="YYYY-MM-DD, default today.")
    i.add_argument("--valid-until", help="Last day of use, YYYY-MM-DD (inclusive).")
    i.add_argument("--days", type=int, help="Length in days from --issued-on (trial: 30).")
    for name in lk.LIMIT_FIELDS:
        i.add_argument(
            f"--{name.replace('_', '-')}",
            dest=name,
            default="default",
            help="Number, or 'unlimited'. Default: the bundle's value.",
        )
    i.set_defaults(func=issue)

    s = sub.add_parser("show", help="Check a key and print its terms.")
    s.add_argument("key")
    s.add_argument("--public-key", help="PEM file; default: the shipped public key.")
    s.set_defaults(func=show)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
