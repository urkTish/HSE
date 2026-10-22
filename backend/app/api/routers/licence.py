"""Licence status and renewal (trial readiness, package B; D-289…D-298)."""

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses
from app.schemas.licence import LicenceKeyInput, LicenceRead, LicenceStorage, LicenceUsage
from app.services import licence as svc
from app.services.permissions import Principal

router = APIRouter(prefix="/licence", tags=["licence"])


def _usage(used: int, limit: int | None) -> LicenceUsage:
    pct = None if limit is None else (100 if limit == 0 else used * 100 // limit)
    return LicenceUsage(used=used, limit=limit, percent=pct)


def _read(db: Session, p: Principal, st: svc.Status) -> LicenceRead:
    t = st.terms
    store = svc.storage_used(db)
    limit_gb = t.max_storage_gb if t else None
    pct = None
    if limit_gb is not None:
        pct = 100 if limit_gb == 0 else store.used_bytes * 100 // (limit_gb * svc.GB)
    return LicenceRead(
        state=st.state,
        read_only=st.read_only,
        source=st.loaded.source,
        problem=str(st.loaded.problem) if st.loaded.problem else None,
        licence_id=t.licence_id if t else None,
        customer=t.customer if t else None,
        bundle=t.bundle if t else None,
        is_trial=bool(t and t.is_trial),
        issued_on=t.issued_on if t else None,
        valid_until=t.valid_until if t else None,
        days_left=st.days_left,
        data_deletion_after=st.data_deletion_after,
        installed_at=st.loaded.installed_at,
        projects=_usage(svc.open_projects(db), t.max_projects if t else None),
        users=_usage(svc.counted_users(db), t.max_users if t else None),
        ai_questions_month=_usage(
            svc.ai_questions_this_month(db), t.ai_questions_per_month if t else None
        ),
        storage=LicenceStorage(
            files_bytes=store.files_bytes,
            database_bytes=store.database_bytes,
            used_bytes=store.used_bytes,
            limit_gb=limit_gb,
            percent=pct,
            warning=pct is not None and pct >= svc.STORAGE_WARNING_PERCENT,
        ),
        can_manage=p.is_manager,
    )


@router.get(
    "",
    response_model=LicenceRead,
    summary="Licence state, days left and usage against the licence caps",
    description="Any signed-in user (the shell shows the trial / expiry banner). No key = state "
    "`none` and every limit null (unlimited).",
    responses=error_responses(401, 403),
)
def get_licence(user: CurrentUser, db: DB) -> LicenceRead:
    return _read(db, user, svc.current(db))


@router.put(
    "",
    response_model=LicenceRead,
    summary="Enter a new licence key (renewal, no restart)",
    description="HSE Manager only. Allowed in read-only mode. The key's signature is checked "
    "against the public key shipped with the app; 422 LICENCE_KEY_INVALID (meta.reason: "
    "malformed, bad_signature, expired, no_public_key, …) otherwise. Every API process uses "
    "the new key within `LICENCE_CACHE_SECONDS`.",
    responses=error_responses(401, 403, 422),
)
def put_licence(body: LicenceKeyInput, user: CurrentUser, db: DB) -> LicenceRead:
    return _read(db, user, svc.install(db, user, body.key))
