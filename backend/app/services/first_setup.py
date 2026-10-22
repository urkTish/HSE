"""First-time setup without seed scripts (D-306).

On an empty install (no users, no `installation` row) one public request creates the
organisation record, the first project and the first administrator (HSE Manager, organisation-
wide), signs that person in and locks the setup for good. An advisory lock serialises two
browsers racing for it; SETUP_TOKEN, when set, must be typed as well."""

from __future__ import annotations

import hmac
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.config import get_settings
from app.core.enums import AuditAction, EmployerType, EntityType, Role, UserStatus
from app.core.errors import ApiError, ErrorCode
from app.core.security import hash_password
from app.core.text import search_blob
from app.models import Installation, RoleAssignment, User
from app.schemas.setup import SetupRequest, SetupStatus
from app.services import audit
from app.services import auth as auth_svc
from app.services import projects as project_svc
from app.services.audit import AuditActor
from app.services.permissions import build_principal

LOCK_KEY = 730_600  # pg_advisory_xact_lock key for the setup


def needed(db: Session) -> bool:
    return db.get(Installation, 1) is None and db.scalar(select(User.id).limit(1)) is None


def status(db: Session) -> SetupStatus:
    inst = db.get(Installation, 1)
    return SetupStatus(
        needed=needed(db),
        token_required=bool(get_settings().setup_token),
        organisation_name_en=inst.organisation_name_en if inst else None,
        organisation_name_ar=inst.organisation_name_ar if inst else None,
    )


def _done() -> ApiError:
    return ApiError(
        409,
        ErrorCode.SETUP_ALREADY_DONE,
        "This installation is already set up. Sign in instead.",
        "تم إعداد هذا النظام مسبقًا. سجّل الدخول بدلًا من ذلك.",
    )


def run(db: Session, body: SetupRequest) -> tuple[auth_svc.IssuedSession, User]:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
    if not needed(db):
        raise _done()
    expected = get_settings().setup_token
    if expected and not hmac.compare_digest((body.setup_token or "").encode(), expected.encode()):
        raise ApiError(
            403,
            ErrorCode.FORBIDDEN,
            "The setup code is not correct.",
            "رمز الإعداد غير صحيح.",
        )
    a = body.admin
    email = str(a.email).strip().lower()
    auth_svc.check_password(a.password, email, "admin.password")
    auth_svc._check_notice_version(body.privacy_notice_version)
    current = now()
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name_en=a.full_name_en.strip(),
        full_name_ar=(a.full_name_ar or "").strip() or None,
        mobile=a.mobile,
        employer_type=EmployerType.client,
        job_title=a.job_title,
        preferred_language=a.preferred_language,
        status=UserStatus.active,
        password_hash=hash_password(a.password),
        activated_at=current,
        last_login_at=current,
        privacy_notice_version=body.privacy_notice_version,
        privacy_notice_ack_at=current,
        search_text=search_blob(a.full_name_en, a.full_name_ar, email),
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            id=uuid.uuid4(),
            user_id=user.id,
            role=Role.hse_manager,
            project_id=None,
            site_ids=[],
            valid_from=today(),
            created_at=current,
        )
    )
    db.flush()
    p = build_principal(db, user, None)
    project = project_svc.create(db, p, body.project)
    db.add(
        Installation(
            id=1,
            organisation_name_en=body.organisation_name_en.strip(),
            organisation_name_ar=body.organisation_name_ar.strip(),
            setup_completed_at=current,
            setup_by_user_id=user.id,
        )
    )
    actor = AuditActor(user.id, Role.hse_manager)
    audit.record(
        db,
        AuditAction.create,
        actor,
        entity_type=EntityType.user,
        entity_id=user.id,
        after={"email": email, "role": Role.hse_manager},
        details={
            "first_time_setup": True,
            "organisation_name_en": body.organisation_name_en,
            "project_code": project.code,
        },
    )
    audit.record(
        db,
        AuditAction.privacy_notice_acknowledged,
        actor,
        entity_type=EntityType.user,
        entity_id=user.id,
        after={"privacy_notice_version": body.privacy_notice_version},
    )
    issued = auth_svc.create_session(db, user)
    audit.record(
        db, AuditAction.login_success, actor, entity_type=EntityType.user, entity_id=user.id
    )
    return issued, user
