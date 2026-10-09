"""Helpers shared by the Phase 6d services (spec 6d-field-assurance): settings (§3.14 defaults
merged over the stored values), weeks (ISP-3, §6.5), photos (EXE-5: decode, size / type limits,
EXIF and location stripped), corrective actions from findings (FND-3, AUD-4), visibility helpers
and the helpers re-exported from the 6b common module."""

from __future__ import annotations

import base64
import binascii
import struct
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role, WeekStart
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import AttachmentOwner, CaPriority, CaSourceType, CaStatus, ControlLevel
from app.models import (
    CorrectiveAction,
    FieldSettings,
    Project,
    ProjectEngagement,
    ProjectSettings,
    Site,
    Zone,
)
from app.services import audit
from app.services.heat.common import (
    at_local,
    day_start,
    err,
    local_day,
    managers,
    need,
    next_seq,
    officers,
    pcode,
    project,
    reason,
    record,
    reps,
    send,
    site_engineers,
    tier1_on_site,
    user_ref,
    zone_map,
)
from app.services.heat.common import once as _once
from app.services.permissions import Grant, Principal, forbidden_error

__all__ = [
    "at_local",
    "day_start",
    "err",
    "local_day",
    "managers",
    "need",
    "next_seq",
    "officers",
    "pcode",
    "project",
    "reason",
    "record",
    "reps",
    "send",
    "site_engineers",
    "tier1_on_site",
    "user_ref",
    "zone_map",
]

D = Decimal
C = Capability

DEFAULTS: dict[str, Any] = {
    "inspection_pass_mark_pct": "85.0",
    "repeat_finding_days": 30,
    "contractor_audit_months": 6,
    "system_audit_months": 12,
    "first_audit_grace_days": 60,
    "audit_report_days": 7,
    "offline_submit_max_hours": 72,
    "offline_cache_hours": 72,
    "tbt_min_minutes": 10,
    "tbt_edit_window_hours": 24,
    "campaign_default_days": 7,
    "inspection_coverage_warning_pct": "90.0",
    "audit_programme_warning_pct": "90.0",
    "tbt_reach_warning_pct": "85.0",
    "critical_fail_warning_per_100": "5.00",
    "photo_retention_months": 24,
}
PCT_KEYS = (
    "inspection_pass_mark_pct",
    "inspection_coverage_warning_pct",
    "audit_programme_warning_pct",
    "tbt_reach_warning_pct",
    "critical_fail_warning_per_100",
)


@dataclass
class Cfg:
    project_id: uuid.UUID
    template_from: date | None
    toolbox_from: date | None
    v: dict[str, Any]

    def __getitem__(self, k: str) -> Any:
        return self.v[k]

    def dec(self, k: str) -> Decimal:
        return D(str(self.v[k]))

    def templates_required(self, d: date) -> bool:
        """ISP-1 / EXE-3 from inspection_template_required_from."""
        return self.template_from is not None and d >= self.template_from

    def register_day(self, d: date) -> bool:
        """SRC-2: toolbox talks from the register on days ≥ toolbox_register_from."""
        return self.toolbox_from is not None and d >= self.toolbox_from


def settings_row(db: Session, project_id: uuid.UUID) -> FieldSettings:
    s = db.get(FieldSettings, project_id)
    if s is None:
        s = FieldSettings(project_id=project_id, values={})
        db.add(s)
        db.flush()
    return s


def cfg(db: Session, project_id: uuid.UUID) -> Cfg:
    cache: dict[uuid.UUID, Cfg] = db.info.setdefault("field_cfg", {})
    if project_id not in cache:
        s = db.get(FieldSettings, project_id)
        v = {**DEFAULTS, **((s.values or {}) if s else {})}
        cache[project_id] = Cfg(
            project_id,
            s.inspection_template_required_from if s else None,
            s.toolbox_register_from if s else None,
            v,
        )
    return cache[project_id]


def clear_cache(db: Session) -> None:
    db.info.pop("field_cfg", None)


def q1(v: Decimal) -> Decimal:
    return v.quantize(D("0.1"), rounding=ROUND_HALF_UP)


def pct_str(v: Decimal | None) -> str | None:
    return None if v is None else str(q1(v))


def w3(v: Decimal | None) -> str:
    return str(D(v or 0).quantize(D("0.001"), rounding=ROUND_HALF_UP))


# ---- weeks (ISP-3, §6.5) -------------------------------------------------------------------------


def week_start_setting(db: Session, project_id: uuid.UUID) -> WeekStart:
    ps = db.get(ProjectSettings, project_id)
    return ps.week_start if ps is not None else WeekStart.sunday


def week_of(db: Session, project_id: uuid.UUID, d: date) -> date:
    """First day of the week containing d."""
    from app.kpi.periods import week_start  # noqa: PLC0415

    return week_start(d, week_start_setting(db, project_id))


def weeks_in(db: Session, project_id: uuid.UUID, d0: date, d1: date, as_of: date) -> list[date]:
    """Week start dates whose last day falls in [d0, d1] and ≤ as_of (§6.5)."""
    ws = week_of(db, project_id, d0)
    out: list[date] = []
    while ws <= d1:
        last = ws + timedelta(days=6)
        if d0 <= last <= d1 and last <= as_of:
            out.append(ws)
        ws += timedelta(days=7)
    return out


# ---- photos (EXE-5, P6d-3) -----------------------------------------------------------------------

MAX_PHOTO = 5 * 1024 * 1024


def _strip_jpeg(b: bytes) -> bytes:
    """Drop APP1…APP15 (EXIF, XMP, GPS, maker data) and COM segments; keep APP0 and image data."""
    if not b.startswith(b"\xff\xd8"):
        return b
    out = bytearray(b[:2])
    i = 2
    while i + 4 <= len(b):
        if b[i] != 0xFF:
            break
        marker = b[i + 1]
        if marker == 0xDA:  # start of scan: the rest is image data
            out += b[i:]
            return bytes(out)
        (length,) = struct.unpack(">H", b[i + 2 : i + 4])
        seg = b[i : i + 2 + length]
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE):
            out += seg
        i += 2 + length
    out += b[i:]
    return bytes(out)


def _strip_png(b: bytes) -> bytes:
    """Drop eXIf and text chunks (tEXt, zTXt, iTXt) and the time chunk."""
    sig = b"\x89PNG\r\n\x1a\n"
    if not b.startswith(sig):
        return b
    out = bytearray(sig)
    i = len(sig)
    while i + 8 <= len(b):
        (n,) = struct.unpack(">I", b[i : i + 4])
        kind = b[i + 4 : i + 8]
        chunk = b[i : i + 12 + n]
        if kind not in (b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"):
            out += chunk
        i += 12 + n
    return bytes(out)


def strip_metadata(b: bytes) -> bytes:
    return _strip_png(_strip_jpeg(b))


def decode_photo(p: Any, fld: str) -> tuple[bytes, str]:
    try:
        raw = base64.b64decode(p.content_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise validation_error(fld, "The photo is not valid base64.") from e
    if len(raw) > MAX_PHOTO:
        raise ApiError(422, ErrorCode.FILE_TOO_LARGE, "Photos must be 5 MB or smaller.",
                       "الحد الأقصى للصورة 5 ميغابايت.")  # fmt: skip
    if raw.startswith(b"\xff\xd8"):
        return strip_metadata(raw), "image/jpeg"
    if raw.startswith(b"\x89PNG"):
        return strip_metadata(raw), "image/png"
    raise validation_error(fld, "Photos must be JPG or PNG.")


def store_photos(
    db: Session,
    owner: AttachmentOwner,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    photos: Iterable[Any],
    user_id: uuid.UUID,
    fld: str,
) -> list[uuid.UUID]:
    from app.services import attachments  # noqa: PLC0415

    ids: list[uuid.UUID] = []
    for i, p in enumerate(photos):
        content, ctype = decode_photo(p, f"{fld}[{i}]")
        a = attachments.store(db, owner, owner_id, project_id, p.file_name, content, ctype, user_id)
        ids.append(a.id)
    return ids


# ---- people, scope -------------------------------------------------------------------------------


def roles_on(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> set[Role]:
    from app.services.hse_common import user_roles  # noqa: PLC0415

    return user_roles(db, user_id, project_id)


def tree_of(db: Session, engagement_id: uuid.UUID | None) -> set[uuid.UUID]:
    """The engagement and its ancestors (the tree a C-scope rep may belong to)."""
    out: set[uuid.UUID] = set()
    e = db.get(ProjectEngagement, engagement_id) if engagement_id else None
    while e is not None and e.id not in out:
        out.add(e.id)
        e = db.get(ProjectEngagement, e.parent_engagement_id) if e.parent_engagement_id else None
    return out


def tier1_of(db: Session, engagement_id: uuid.UUID | None) -> uuid.UUID | None:
    e = db.get(ProjectEngagement, engagement_id) if engagement_id else None
    while e is not None and e.parent_engagement_id is not None:
        e = db.get(ProjectEngagement, e.parent_engagement_id)
    return e.id if e else None


def first_rep(
    db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID | None
) -> uuid.UUID | None:
    """FND-3 owner: the first active Contractor HSE Rep of the engagement, else of its tier-1."""
    from app.services.hse_common import contractor_reps  # noqa: PLC0415

    for e in (engagement_id, tier1_of(db, engagement_id)):
        rs = contractor_reps(db, project_id, e)
        if rs:
            return rs[0]
    return None


def view_grant(p: Principal, project_id: uuid.UUID) -> Grant:
    g = p.grant(project_id, C.field_view)
    if g is None:
        raise forbidden_error()
    return g


def in_scope(g: Grant | None, site_id: uuid.UUID | None, eng_id: uuid.UUID | None) -> bool:
    from app.services.hse_common import covers  # noqa: PLC0415

    return covers(g, site_id, eng_id)


def is_viewer(p: Principal, project_id: uuid.UUID) -> bool:
    """Viewer/Client: aggregates and registers, never photos or names (P6d-3, P6d-4)."""
    if p.is_manager:
        return False
    sc = p.projects.get(project_id)
    return sc is not None and sc.read_only


def site_of(db: Session, site_id: uuid.UUID) -> Site:
    s = db.get(Site, site_id)
    if s is None:
        raise validation_error("site_id", "Unknown site.")
    return s


def zone_type(db: Session, zone_id: uuid.UUID | None) -> str | None:
    z = db.get(Zone, zone_id) if zone_id else None
    return z.zone_type.value if z is not None else None


def once(db: Session, key: str) -> bool:
    return _once(db, key)


# ---- corrective actions (FND-3, AUD-4) -----------------------------------------------------------


PRIORITY_OF = {
    "critical": CaPriority.critical,
    "major": CaPriority.high,
    "minor": CaPriority.medium,
    "major_nc": CaPriority.high,
    "minor_nc": CaPriority.medium,
    "observation": CaPriority.low,
    "ofi": CaPriority.low,
}


def make_ca(
    db: Session,
    proj: Project,
    source_type: CaSourceType,
    source_id: uuid.UUID,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    severity: str,
    title: str,
    description: str,
    control: ControlLevel | None,
    inspector_id: uuid.UUID | None,
    created_by: uuid.UUID | None,
) -> CorrectiveAction:
    """A Phase 1 CA for a finding: priority by severity, due per ca_due_days, responsible = the
    finding's engagement (else the site's tier-1), owner = the first rep of the engagement (else
    of its tier-1, else an HSE Officer), verifier = the inspector when CA-5 allows, else the
    project's first HSE Officer."""
    from app.services import hse_settings  # noqa: PLC0415
    from app.services.hse_common import make_ref  # noqa: PLC0415

    pr = PRIORITY_OF[severity]
    eng = engagement_id or tier1_on_site(db, proj.id, site_id)
    offs = sorted(officers(db, proj.id)) or sorted(managers(db))
    owner = first_rep(db, proj.id, eng) or offs[0]
    verifier = offs[0] if offs[0] != owner else (offs[1:] or sorted(managers(db)))[0]
    if inspector_id is not None and inspector_id != owner:
        roles = roles_on(db, inspector_id, proj.id)
        allowed = {Role.hse_officer, Role.hse_manager}
        if pr not in (CaPriority.critical, CaPriority.high):
            allowed |= {Role.site_engineer}
        if roles & allowed:
            verifier = inspector_id
    created = local_day()
    s = hse_settings.get(db, proj.id)
    due = created + timedelta(days=hse_settings.ca_due_days(s, pr))
    seq = next_seq(db, CorrectiveAction, proj.id, created.year)
    ca = CorrectiveAction(
        id=uuid.uuid4(),
        project_id=proj.id,
        ref=make_ref("CA", proj.code, created.year, seq, 5),
        year=created.year,
        seq=seq,
        source_type=source_type,
        source_id=source_id,
        site_id=site_id,
        zone_id=zone_id,
        responsible_engagement_id=eng,
        title=title[:150],
        description=description,
        control_level=control or ControlLevel.administrative,
        priority=pr,
        owner_id=owner,
        verifier_id=verifier,
        created_date=created,
        due_date=due,
        original_due_date=due,
        status=CaStatus.open,
        created_by_user_id=created_by,
        alerts_sent=[],
    )
    db.add(ca)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        audit.SYSTEM,
        entity_type=EntityType.corrective_action,
        entity_id=ca.id,
        project_id=proj.id,
        after={"ref": ca.ref, "source_type": source_type.value},
    )
    send(
        db,
        [owner],
        NotificationKind.ca_assigned,
        f"{ca.ref} assigned to you: {ca.title}",
        f"تم إسناد {ca.ref} إليك",
        proj.id,
        EntityType.corrective_action,
        ca.id,
        email=True,
    )
    return ca


def ca_info(db: Session, ca_id: uuid.UUID | None) -> tuple[str | None, CaStatus | None]:
    ca = db.get(CorrectiveAction, ca_id) if ca_id else None
    return (ca.ref, ca.status) if ca else (None, None)


def offline_label(delay: int | None, completed_at: datetime | None) -> str:
    """EXE-7: alert suffix for submissions received more than 15 minutes late."""
    if not delay or completed_at is None:
        return ""
    loc = completed_at.astimezone(acommon_tz())
    return f" (recorded offline at {loc:%H:%M})"


def offline_label_ar(delay: int | None, completed_at: datetime | None) -> str:
    if not delay or completed_at is None:
        return ""
    loc = completed_at.astimezone(acommon_tz())
    return f" (سُجل دون اتصال الساعة {loc:%H:%M})"


def acommon_tz() -> Any:
    from app.services.access import common as acommon  # noqa: PLC0415

    return acommon.RIYADH


def p18(text: str | None) -> bool:
    """P1-8 scan (possible ID number)."""
    from app.services.hse_common import POSSIBLE_ID  # noqa: PLC0415

    return bool(text and POSSIBLE_ID.search(text))
