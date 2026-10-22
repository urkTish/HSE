"""Clear a user's two-step verification from the server shell (D-300).

For the case the UI cannot cover: the only HSE Manager lost their phone and their recovery codes.
Run on the server: `docker compose exec backend python -m app.mfa_reset someone@example.com`.
The user's sessions end; they sign in with their password and set it up again."""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.core.enums import AuditAction, EntityType
from app.db.session import get_sessionmaker
from app.models import User
from app.services import audit, mfa
from app.services.auth import revoke_sessions


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.mfa_reset <email>", file=sys.stderr)
        return 2
    email = argv[0].strip().lower()
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"no user with email {email}", file=sys.stderr)
            return 1
        mfa._clear(db, user)
        user.mfa_required_since = None
        revoke_sessions(db, user.id, "mfa_reset")
        audit.record(db, AuditAction.mfa_changed, audit.SYSTEM, entity_type=EntityType.user,
                     entity_id=user.id, details={"change": "reset_from_server_shell"})  # fmt: skip
        db.commit()
    print(f"two-step verification cleared for {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
