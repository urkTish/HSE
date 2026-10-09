"""Helpers shared by the Phase 2 services (spec 2-access-permits): settings, ID protection
(encryption, blind index, masking), QR tokens, date arithmetic, scope checks and refs."""

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import QrKind, QrTokenStatus, WorkerIdType
from app.core.clock import now, today
from app.core.config import get_settings
from app.core.enums import Capability
from app.core.errors import ApiError, ErrorCode, validation_error
from app.kpi.periods import add_months
from app.models import (
    AccessSettings,
    Contractor,
    Project,
    ProjectEngagement,
    QrToken,
    Vehicle,
    Worker,
)
from app.schemas.access_common import VehicleRef, WorkerRef
from app.services.permissions import Grant, Principal, forbidden_error

RIYADH = ZoneInfo("Asia/Riyadh")
TWO = Decimal("0.01")
FT = Decimal("0.3048")

ID_PATTERNS = {
    WorkerIdType.iqama: re.compile(r"^2\d{9}$"),
    WorkerIdType.national_id: re.compile(r"^1\d{9}$"),
    WorkerIdType.gcc_id: re.compile(r"^[A-Z0-9]{6,15}$"),
    WorkerIdType.passport: re.compile(r"^[A-Z0-9]{6,9}$"),
}

# ---- settings ------------------------------------------------------------------------------------


def settings(db: Session, project_id: uuid.UUID) -> AccessSettings:
    """§3.22 settings row of the project (created with the defaults on first use)."""
    s = db.get(AccessSettings, project_id)
    if s is None:
        s = AccessSettings(project_id=project_id)
        for col in AccessSettings.__table__.columns:
            if getattr(s, col.key) is None and col.default is not None:
                arg = col.default.arg
                setattr(s, col.key, arg(None) if callable(arg) else arg)
        s.hook_policy = s.hook_policy or {}
        db.add(s)
        db.flush()
    return s


# ---- time ---------------------------------------------------------------------------------------


def local(ts: datetime) -> datetime:
    return ts.astimezone(RIYADH)


def local_day(ts: datetime) -> date:
    return ts.astimezone(RIYADH).date()


def local_midnight_utc(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), RIYADH).astimezone(UTC)


def at_local(d: date, t: time) -> datetime:
    return datetime.combine(d, t, RIYADH).astimezone(UTC)


def validity_until(start: date, months: int | None, days: int | None = None) -> date:
    """§6.1: add_months(start, m) − 1 day (clamped); visitor courses start + days − 1."""
    if days:
        return start + timedelta(days=days - 1)
    assert months is not None  # noqa: S101
    return add_months(start, months) - timedelta(days=1)


def days_left(d: date | None, day: date | None = None) -> int | None:
    return None if d is None else (d - (day or today())).days


def notam_format(ts: datetime | None) -> str | None:
    """NT-3: YYMMDDHHMM UTC."""
    return None if ts is None else ts.astimezone(UTC).strftime("%y%m%d%H%M")


def q2(v: Decimal) -> Decimal:
    return v.quantize(TWO, rounding=ROUND_HALF_UP)


def to_ft(m: Decimal) -> Decimal:
    """OB-9: 1 ft = 0.3048 m exactly; 2 dp half-up."""
    return q2(m / FT)


# ---- ID protection (P2-2, WK-2..WK-5) -------------------------------------------------------


def normalise_id(number: str) -> str:
    return re.sub(r"[\s-]", "", number).upper()


def check_id(id_type: WorkerIdType, number: str, passport_country: str | None) -> str:
    n = normalise_id(number)
    if not ID_PATTERNS[id_type].match(n):
        raise validation_error("id_number", f"Not a valid {id_type.value} number.")
    if id_type == WorkerIdType.passport and not passport_country:
        raise validation_error("passport_country", "The passport country is required.")
    return n


def blind_index(id_type: WorkerIdType, number: str, passport_country: str | None) -> str:
    """HMAC-SHA256(id_type ‖ normalised number ‖ passport country) with its own key."""
    key = get_settings().blind_index_key.encode()
    msg = "|".join(
        [
            id_type.value,
            normalise_id(number),
            (passport_country or "").upper() if id_type == WorkerIdType.passport else "",
        ]
    )
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def mask_worker_id(id_type: WorkerIdType, number: str) -> str:
    """WK-4: Saudi IDs first digit + 7 `*` + last 2; GCC/passport first 2 + `*` + last 2."""
    if id_type in (WorkerIdType.iqama, WorkerIdType.national_id):
        return crypto.mask_id(number)
    if len(number) <= 4:
        return "*" * len(number)
    return number[:2] + "*" * (len(number) - 4) + number[-2:]


def set_worker_id(w: Worker, id_type: WorkerIdType, number: str, country: str | None) -> None:
    n = check_id(id_type, number, country)
    w.id_type = id_type
    w.id_number_enc = crypto.encrypt(n)
    w.id_number_bidx = blind_index(id_type, n, country)
    w.id_number_masked = mask_worker_id(id_type, n)
    w.passport_country = country.upper() if country and id_type == WorkerIdType.passport else None


# ---- QR tokens (§3.20) ----------------------------------------------------------------------

QR_RE = re.compile(r"^HSE2:(AC|VS|WP|PT|EQ|TR|EA|MP):([A-Za-z0-9_-]{22})(?:\.[A-Za-z0-9_-]+)?$")


def new_qr_token() -> str:
    """22-char base64url of 128 random bits."""
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip("=")


def payload(t: QrToken) -> str:
    return f"HSE2:{t.kind.value}:{t.token}"


def issue_qr(
    db: Session, kind: QrKind, project_id: uuid.UUID, subject_id: uuid.UUID, printed_ref: str
) -> QrToken:
    t = QrToken(
        id=uuid.uuid4(),
        token=new_qr_token(),
        kind=kind,
        project_id=project_id,
        subject_id=subject_id,
        printed_ref=printed_ref,
        status=QrTokenStatus.active,
        created_at=now(),
    )
    db.add(t)
    db.flush()
    return t


def active_qr(db: Session, subject_id: uuid.UUID) -> QrToken | None:
    return db.scalar(
        select(QrToken).where(
            QrToken.subject_id == subject_id, QrToken.status == QrTokenStatus.active
        )
    )


def latest_qr(db: Session, subject_id: uuid.UUID) -> QrToken | None:
    return db.scalar(
        select(QrToken).where(QrToken.subject_id == subject_id).order_by(QrToken.created_at.desc())
    )


def end_qr(db: Session, subject_id: uuid.UUID, status: QrTokenStatus, lost: bool = False) -> None:
    for t in db.scalars(
        select(QrToken).where(
            QrToken.subject_id == subject_id, QrToken.status == QrTokenStatus.active
        )
    ):
        t.status = status
        t.lost = lost
        t.ended_at = now()


# ---- project / scope -----------------------------------------------------------------------------


def require_airport(project: Project) -> None:
    """AP-2: passes, ADPs, AVPs, vehicles and NOTAM records only on airport projects."""
    if not project.is_airport:
        raise ApiError(
            422,
            ErrorCode.NOT_AIRPORT_PROJECT,
            f"{project.code} is not an airport project.",
            "هذا المشروع ليس مشروع مطار.",
        )


def grant_covers(
    g: Grant | None, site_ids: Iterable[uuid.UUID] | None, engagement_id: uuid.UUID | None
) -> bool:
    if g is None:
        return False
    sites = list(site_ids or [])
    if g.site_ids is not None and sites and not any(s in g.site_ids for s in sites):
        return False
    return g.engagement_ids is None or (
        engagement_id is not None and engagement_id in g.engagement_ids
    )


def require_cap(
    p: Principal,
    project_id: uuid.UUID,
    cap: Capability,
    site_ids: Iterable[uuid.UUID] | None = None,
    engagement_id: uuid.UUID | None = None,
    write: bool = True,
) -> Grant:
    if write:
        p.ensure_writer()
    g = p.grant(project_id, cap)
    if g is None:
        if write:
            p.require(project_id, cap)  # raises the right 403
        raise forbidden_error()
    if not grant_covers(g, site_ids, engagement_id):
        raise forbidden_error("This record is outside your scope.")
    return g


def engagement_contractor(db: Session, engagement_id: uuid.UUID | None) -> Contractor | None:
    if engagement_id is None:
        return None
    e = db.get(ProjectEngagement, engagement_id)
    return e.contractor if e else None


def engagement_ancestors(db: Session, engagement_id: uuid.UUID) -> list[uuid.UUID]:
    """The engagement and its parents up to the tier-1 root."""
    out: list[uuid.UUID] = []
    cur: uuid.UUID | None = engagement_id
    while cur is not None and cur not in out:
        out.append(cur)
        e = db.get(ProjectEngagement, cur)
        cur = e.parent_engagement_id if e else None
    return out


# ---- refs ---------------------------------------------------------------------------------------


def can_see_names(p: Principal | None, project_id: uuid.UUID | None) -> bool:
    """Names of workers only for capability 46 holders (WA-19, KA-4)."""
    if p is None:
        return True
    return p.grant(project_id, Capability.worker_view) is not None


def worker_ref(w: Worker, names: bool) -> WorkerRef:
    return WorkerRef(
        id=w.id,
        worker_no=w.worker_no,
        full_name_en=w.full_name_en if names else None,
        full_name_ar=w.full_name_ar if names else None,
        status=w.status,
    )


def vehicle_ref(v: Vehicle) -> VehicleRef:
    return VehicleRef(id=v.id, vehicle_no=v.vehicle_no, fleet_no=v.fleet_no, category=v.category)


def plate_display(v: Vehicle) -> str | None:
    if not v.plate_digits:
        return None
    return f"{v.plate_letters_ar or ''} {v.plate_digits}".strip()


def reason_text(text: str | None, minimum: int = 10) -> str:
    if not text or len(text.strip()) < minimum:
        raise validation_error("reason_text", f"Give a reason of at least {minimum} characters.")
    return text.strip()


def jsonable(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, uuid.UUID | date | datetime | Decimal):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = [str(x) if isinstance(x, uuid.UUID | date | Decimal) else x for x in v]
        else:
            out[k] = v
    return out
