"""Licence state, renewal and enforcement (trial readiness, package B; D-289…D-298).

* No key anywhere (database, LICENCE_KEY, LICENCE_FILE) → state ``none``: unlimited, nothing
  enforced (development, tests, installs that are not sold).
* A valid key on or before ``valid_until`` (Riyadh date) → ``active``: the caps apply.
* After ``valid_until`` → ``expired``; a key that fails the signature check → ``invalid``. Both are
  read-only: GET requests, exports and a short list of sign-in, viewing and life-safety actions
  stay open (``READ_ONLY_ALLOWED``); every other write answers 403 LICENCE_READ_ONLY.

The active key is cached per process for ``licence_cache_seconds``; installing a key clears the
cache of the process that took it, and every other worker reloads within that time, so a renewal
needs no restart.
"""

import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app.core import licence_key as lk
from app.core.clock import DEFAULT_TZ, now, today
from app.core.config import API_PREFIX, get_settings
from app.core.enums import AuditAction, EntityType, ProjectStatus, UserStatus
from app.core.errors import ApiError, ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.db.session import get_sessionmaker
from app.models import AiLog, Attachment, LicenceKey, Project, User
from app.services import audit
from app.services.permissions import Principal, forbidden_error

GB = 1024**3
STORAGE_WARNING_PERCENT = 80
TRIAL_DATA_KEPT_DAYS = 30  # trial terms: data deleted 30 days after expiry if not converted
# Files the platform writes for a read (export files) are never refused for storage.
STORAGE_EXEMPT = frozenset({AttachmentOwner.xp_export_file})

# Writes that stay open in read-only mode (paths after /api/v1, any method). Sign-in and the
# licence page itself; viewing actions that answer with a link, a lookup or a preview that
# stores nothing; the viewer's own preferences; exports; and the
# life-safety flows (gate checks, musters, emergency events), which must never stop on a site.
READ_ONLY_ALLOWED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"/auth/.*",
        r"/licence",
        r"/gate-device/(login|logout)",
        r"/gate-checks",
        r"/certification-checks",
        r"/notifications/(read-all|[^/]+/read)",
        r"/attachments/[^/]+/signed-url",
        r"/(personnel-certificates|training-records|fitness-assessments)/[^/]+/scan-url",
        r"/workers/[^/]+/id-number/unmask",
        r"/(workers|equipment)/lookup",
        r"/audit-log/verify",
        r"/exports",
        r"/projects/[^/]+/journey-plans/hint",
        r"/(obstacle-clearances|.+/gas-tests|projects/[^/]+/[a-z-]+)/preview",  # compute only
        r"/dashboard/preferences",  # the viewer's own tile layout, saved by the dashboard
        r"/emergency/muster-(session|scan)",
        r"/musters/[^/]+/(scan|counts|entries/[^/]+/(tick|resolve))",
        r"/projects/[^/]+/emergency-events",
        r"/emergency-events/[^/]+(/transitions|/review)?",
    )
)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class Loaded:
    """The key this install runs on, as read from its source (cached)."""

    source: str | None  # "database" | "environment" | None
    terms: lk.LicenceTerms | None
    problem: lk.LicenceKeyError | None
    installed_at: datetime | None


@dataclass(frozen=True)
class Status:
    loaded: Loaded
    today: date

    @property
    def terms(self) -> lk.LicenceTerms | None:
        return self.loaded.terms

    @property
    def state(self) -> str:
        if self.loaded.problem is not None:
            return "invalid"
        t = self.loaded.terms
        if t is None:
            return "none"
        return "expired" if self.today > t.valid_until else "active"

    @property
    def read_only(self) -> bool:
        return self.state in ("expired", "invalid")

    @property
    def active_terms(self) -> lk.LicenceTerms | None:
        """Terms whose caps apply now (None: unlimited, or read-only anyway)."""
        return self.terms if self.state == "active" else None

    @property
    def days_left(self) -> int | None:
        t = self.terms
        return None if t is None else (t.valid_until - self.today).days

    @property
    def data_deletion_after(self) -> date | None:
        t = self.terms
        if t is None or not t.is_trial:
            return None
        return t.valid_until + timedelta(days=TRIAL_DATA_KEPT_DAYS)


# ---- loading and cache --------------------------------------------------------------------------

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, Any]] = {}


def invalidate() -> None:
    with _LOCK:
        _CACHE.clear()


def _cached(name: str, build: Any) -> Any:
    ttl = get_settings().licence_cache_seconds
    with _LOCK:
        hit = _CACHE.get(name)
        if ttl > 0 and hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]
    value = build()
    if ttl > 0:
        with _LOCK:
            _CACHE[name] = (time.monotonic(), value)
    return value


def public_key() -> Any:
    try:
        return lk.shipped_public_key(get_settings().licence_public_key)
    except ValueError as exc:  # misconfigured LICENCE_PUBLIC_KEY / file
        raise lk.LicenceKeyError("bad_public_key", "The licence public key is damaged.") from exc


def _configured_key() -> str | None:
    s = get_settings()
    if s.licence_key and s.licence_key.strip():
        return s.licence_key
    if s.licence_file:
        path = Path(s.licence_file)
        # A configured but missing file is a problem, not "no licence": it never unlocks.
        return path.read_text(encoding="utf-8") if path.is_file() else "missing-licence-file"
    return None


def _load(db: Session) -> Loaded:
    row = db.scalar(select(LicenceKey).order_by(LicenceKey.installed_at.desc()).limit(1))
    key, source, at = (row.key, "database", row.installed_at) if row else (None, None, None)
    if key is None:
        key = _configured_key()
        source = "environment" if key else None
    if not key:
        return Loaded(None, None, None, None)
    try:
        return Loaded(source, lk.verify(key, public_key()), None, at)
    except lk.LicenceKeyError as exc:
        return Loaded(source, None, exc, at)


def current(db: Session | None = None) -> Status:
    def build() -> Loaded:
        if db is not None:
            return _load(db)
        with get_sessionmaker()() as own:
            return _load(own)

    return Status(_cached("loaded", build), today(DEFAULT_TZ))


# ---- read-only guard ----------------------------------------------------------------------------


def read_only_error(st: Status) -> ApiError:
    if st.state == "invalid":
        en = "The licence key of this install is not valid."
        ar = "مفتاح الترخيص لهذا النظام غير صالح."
    else:
        until = st.terms.valid_until.isoformat() if st.terms else ""
        en = f"The licence ended on {until}."
        ar = f"انتهى الترخيص في {until}."
    return ApiError(
        403,
        ErrorCode.LICENCE_READ_ONLY,
        f"{en} The platform is read-only: you can view and export, but not add or change "
        "records. Ask your administrator for a new licence key.",
        f"{ar} المنصة الآن للقراءة فقط: يمكنك العرض والتصدير دون إضافة السجلات أو تعديلها. "
        "اطلب من مسؤول النظام مفتاح ترخيص جديدًا.",
        meta={"state": st.state},
    )


def write_allowed(method: str, path: str) -> bool:
    if method.upper() in SAFE_METHODS:
        return True
    if not path.startswith(API_PREFIX):
        return True
    rest = path[len(API_PREFIX) :]
    return any(p.fullmatch(rest) for p in READ_ONLY_ALLOWED)


def read_only_guard(request: Request) -> None:
    """App-wide dependency: in read-only mode, refuse writes outside READ_ONLY_ALLOWED."""
    if write_allowed(request.method, request.url.path):
        return
    st = current()
    if st.read_only:
        raise read_only_error(st)


# ---- caps ---------------------------------------------------------------------------------------

_LIMIT_TEXT = {
    "projects": (
        "Your licence allows {max} open project(s) and this install already has {used}. "
        "Close a project or ask for a larger licence.",
        "يسمح ترخيصك بعدد {max} من المشاريع المفتوحة، ويوجد حاليًا {used}. "
        "أغلق مشروعًا أو اطلب ترخيصًا أكبر.",
    ),
    "users": (
        "Your licence allows {max} users and this install already has {used}. "
        "Deactivate a user or ask for a larger licence.",
        "يسمح ترخيصك بعدد {max} من المستخدمين، ويوجد حاليًا {used}. "
        "عطّل مستخدمًا أو اطلب ترخيصًا أكبر.",
    ),
    "ai_questions": (
        "The AI assistant questions in your licence for this month are used up ({max}). "
        "They renew on the 1st of next month.",
        "تم استهلاك أسئلة المساعد الذكي المسموح بها في ترخيصك لهذا الشهر ({max}). "
        "يتجدد الرصيد في أول الشهر القادم.",
    ),
    "storage": (
        "The storage in your licence is full ({max} GB). Remove old files or ask for more storage.",
        "المساحة التخزينية في ترخيصك ممتلئة ({max} غيغابايت). احذف ملفات قديمة أو اطلب "
        "مساحة إضافية.",
    ),
}


def limit_error(
    limit: str, maximum: int, used: int, status: int = 409, headers: dict[str, str] | None = None
) -> ApiError:
    en, ar = _LIMIT_TEXT[limit]
    return ApiError(
        status,
        ErrorCode.LICENCE_LIMIT_REACHED,
        en.format(max=maximum, used=used),
        ar.format(max=maximum, used=used),
        headers=headers,
        meta={"limit": limit, "max": maximum, "used": used},
    )


def open_projects(db: Session) -> int:
    q = select(func.count()).select_from(Project).where(Project.status != ProjectStatus.closed)
    return int(db.scalar(q) or 0)


def counted_users(db: Session) -> int:
    q = select(func.count()).select_from(User).where(User.status != UserStatus.deactivated)
    return int(db.scalar(q) or 0)


def month_start_utc() -> datetime:
    first = today(DEFAULT_TZ).replace(day=1)
    return datetime(first.year, first.month, 1, tzinfo=ZoneInfo(DEFAULT_TZ)).astimezone(UTC)


def next_month_start_utc() -> datetime:
    first = today(DEFAULT_TZ).replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return datetime(nxt.year, nxt.month, 1, tzinfo=ZoneInfo(DEFAULT_TZ)).astimezone(UTC)


def ai_questions_this_month(db: Session) -> int:
    """Asked AI questions this calendar month (Riyadh), whole install. Cached answers and
    failed asks do not count, as for the per-user daily limit (AI-17)."""
    q = (
        select(func.count())
        .select_from(AiLog)
        .where(
            AiLog.kind == "ask",
            AiLog.cached.is_(False),
            AiLog.error_code.is_(None),
            AiLog.created_at >= month_start_utc(),
        )
    )
    return int(db.scalar(q) or 0)


@dataclass(frozen=True)
class Storage:
    files_bytes: int
    database_bytes: int

    @property
    def used_bytes(self) -> int:
        return self.files_bytes + self.database_bytes


def storage_used(db: Session) -> Storage:
    def build() -> Storage:
        files = db.scalar(select(func.coalesce(func.sum(Attachment.size_bytes), 0)))
        database = db.scalar(text("SELECT pg_database_size(current_database())"))
        return Storage(int(files or 0), int(database or 0))

    value: Storage = _cached("storage", build)
    return value


def ensure_can_add_project(db: Session) -> None:
    t = current(db).active_terms
    if t is None or t.max_projects is None:
        return
    used = open_projects(db)
    if used >= t.max_projects:
        raise limit_error("projects", t.max_projects, used)


def ensure_can_add_user(db: Session) -> None:
    t = current(db).active_terms
    if t is None or t.max_users is None:
        return
    used = counted_users(db)
    if used >= t.max_users:
        raise limit_error("users", t.max_users, used)


def ensure_ai_question(db: Session) -> None:
    t = current(db).active_terms
    if t is None or t.ai_questions_per_month is None:
        return
    used = ai_questions_this_month(db)
    if used >= t.ai_questions_per_month:
        wait = int((next_month_start_utc() - now()).total_seconds())
        raise limit_error(
            "ai_questions",
            t.ai_questions_per_month,
            used,
            status=429,
            headers={"Retry-After": str(max(wait, 1))},
        )


def ensure_storage(db: Session, owner: AttachmentOwner, extra_bytes: int) -> None:
    if owner in STORAGE_EXEMPT:
        return
    t = current(db).active_terms
    if t is None or t.max_storage_gb is None:
        return
    st = storage_used(db)
    if st.used_bytes + extra_bytes > t.max_storage_gb * GB:
        raise limit_error("storage", t.max_storage_gb, round(st.used_bytes / GB))


# ---- install (renewal) --------------------------------------------------------------------------


def invalid_key_error(exc: lk.LicenceKeyError) -> ApiError:
    ar = {
        "no_public_key": "لا يحتوي هذا النظام على المفتاح العام للترخيص، "
        "فلا يمكن التحقق من أي مفتاح.",
        "bad_public_key": "المفتاح العام للترخيص في هذا النظام تالف.",
        "bad_signature": "توقيع المفتاح غير مطابق (معدّل أو غير صادر من المورّد).",
        "expired": "انتهت صلاحية هذا المفتاح بالفعل.",
    }.get(exc.reason, "هذا ليس مفتاح ترخيص صالحًا.")
    return ApiError(422, ErrorCode.LICENCE_KEY_INVALID, str(exc), ar, meta={"reason": exc.reason})


def install(db: Session, p: Principal, key: str) -> Status:
    """HSE Manager pastes a new key: checked, stored as the active key, audited. Works in
    read-only mode (that is how an expired install is renewed)."""
    if not p.is_manager:
        raise forbidden_error("Only the HSE Manager can enter a licence key.")
    key = lk.normalise(key)
    try:
        terms = lk.verify(key, public_key())
    except lk.LicenceKeyError as exc:
        raise invalid_key_error(exc) from exc
    day = today(DEFAULT_TZ)
    if day > terms.valid_until:
        raise invalid_key_error(
            lk.LicenceKeyError(
                "expired", f"This key already ended on {terms.valid_until.isoformat()}."
            )
        )
    before = current(db)
    row = LicenceKey(
        key=key,
        licence_id=terms.licence_id,
        customer=terms.customer,
        bundle=terms.bundle,
        valid_until=terms.valid_until,
        installed_at=now(),
        installed_by_user_id=p.user.id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(),
        entity_type=EntityType.licence,
        entity_id=row.id,
        before=_audit_view(before.terms),
        after=_audit_view(terms),
    )
    invalidate()
    event.listen(db, "after_commit", lambda _s: invalidate(), once=True)
    return Status(Loaded("database", terms, None, row.installed_at), day)


def _audit_view(t: lk.LicenceTerms | None) -> dict[str, Any] | None:
    if t is None:
        return None
    return {k: v for k, v in t.to_payload().items() if k != "v"}
