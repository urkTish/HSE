"""Helpers shared by the Q4 services (spec 8-quality Part E): project and capability checks with
the responsible-person scope N (Q-ROL-04), numbers, Riyadh dates, references, pages, PDFs with the
Gregorian and Hijri issue date (Q-RPT-02) and notifications. Reuses the Q0 / Q3 helpers rather than
copying them."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.hijri import hijri_ar, hijri_en
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QRecordType, entity_type_value
from app.models import Project, Site, User
from app.services import audit
from app.services.permissions import Grant, Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import numbering
from app.services.quality import settings as qs
from app.services.quality.q3 import base as b3
from app.services.scorecard import render

C = Capability
S = CapabilityScope
RT = QRecordType
D = Decimal

# re-exported Q3 helpers (same behaviour for every Phase 8 part)
local_day = b3.local_day
day_start = b3.day_start
month_bounds = b3.month_bounds
send = b3.send
holders = b3.holders
resolvers = b3.resolvers
resolves = b3.resolves
sign = b3.sign
signed_by = b3.signed_by
supplier_ref = b3.supplier_ref
customer_ref = b3.customer_ref
page = b3.page
attachment_on = b3.attachment_on
ncr_owner = b3.ncr_owner
operator_engagement = b3.operator_engagement
hide_names = b3.hide_names


def project(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    return qc.get_project(db, p, project_id)


def writer(
    db: Session, p: Principal, project_id: uuid.UUID, cap: Capability, *, allow_n: bool = False
) -> tuple[Project, Grant]:
    """A Q4 write: open project, writer, the capability with a real grant (N only where the
    action is a responsible-person step)."""
    pr = qc.get_project(db, p, project_id)
    qc.writable(pr, p)
    qc.require_profile(db, pr)
    g = p.require(pr.id, cap)
    if g.scope == S.responsible and not allow_n:
        raise forbidden_error("A responsible person signs steps; they do not create records.")
    return pr, g


def viewer(db: Session, p: Principal, project_id: uuid.UUID, *, allow_n: bool = False) -> Grant:
    pr = qc.get_project(db, p, project_id)
    g = p.require(pr.id, C.quality_view)
    if g.scope == S.responsible and not allow_n:
        raise forbidden_error("This list is not shown to the responsible-person scope (Q-ROL-04).")
    return g


def number(db: Session, project: Project, rt: QRecordType, pfx: str | None = None) -> str:
    site = db.scalar(select(Site.code).where(Site.project_id == project.id).limit(1))
    return numbering.assign(db, project, rt, on=qc.project_day(project), site_code=site, pfx=pfx)


def setting(db: Session, project_id: uuid.UUID, key: str) -> Any:
    return qs.value(db, project_id, key)


def today(project: Project) -> date:
    return qc.project_day(project)


def add_months(d: date, months: int) -> date:
    from app.services.train.common import add_months as am  # noqa: PLC0415

    return am(d, months)


def due_after(d: date, months: int) -> date:
    """add_months(d, months) − 1 day (Q-DOC-04, Q-SUP-02)."""
    return add_months(d, months) - timedelta(days=1)


def pct(n: int | Decimal, d: int | Decimal, dp: str = "0.1") -> Decimal | None:
    if not d:
        return None
    return (D(n) * 100 / D(d)).quantize(D(dp), ROUND_HALF_UP)


def q(v: Decimal | float | int | None, dp: str = "0.1") -> Decimal | None:
    if v is None:
        return None
    return D(str(v)).quantize(D(dp), ROUND_HALF_UP)


def user_ref(db: Session, uid: uuid.UUID | None, hide: bool = False) -> dict[str, Any] | None:
    if uid is None:
        return None
    u = db.get(User, uid)
    if u is None:
        return None
    if hide:
        return {"id": u.id, "name_en": "—", "name_ar": "—"}
    return {"id": u.id, "name_en": u.full_name_en, "name_ar": u.full_name_ar or u.full_name_en}


def record(
    db: Session,
    p: Principal | None,
    action: AuditAction,
    rt: QRecordType,
    row: Any,
    project_id: uuid.UUID,
    *,
    before: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(project_id) if p is not None else audit.SYSTEM,
        entity_type=EntityType(entity_type_value(rt)),
        entity_id=row.id,
        project_id=project_id,
        before=before,
        after={k: str(v) for k, v in (details or {}).items()} or None,
    )


def issue_dates(day: date) -> list[tuple[str, ...]]:
    """Q-RPT-02: the issue date in Gregorian and Umm al-Qura Hijri on every Quality PDF."""
    return [
        ("Issue date", "تاريخ الإصدار", day.isoformat()),
        (
            "Issue date (Hijri, Umm al-Qura)",
            "تاريخ الإصدار الهجري، أم القرى",
            hijri_en(day),
            hijri_ar(day),
        ),
    ]


def store_pdfs(
    db: Session,
    owner: AttachmentOwner,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    doc: render.Doc,
    base_name: str,
    by: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Render the EN and AR PDFs with the 6g renderer and store them as generated files."""
    from app.services import attachments  # noqa: PLC0415

    ids = []
    for lang in ("en", "ar"):
        a = attachments.store(
            db,
            owner,
            owner_id,
            project_id,
            f"{base_name}-{lang.upper()}.pdf",
            render.pdf(doc, lang),
            "application/pdf",
            by,
            generated=True,
        )
        ids.append(a.id)
    return ids[0], ids[1]


def table(
    cols: list[tuple[str, str, str]],
    rows: list[dict[str, Any]],
    rows_ar: list[dict[str, Any]] | None = None,
    en: str = "",
    ar: str = "",
) -> render.Table:
    return render.Table(cols, rows, rows_ar=rows_ar, title_en=en, title_ar=ar)


def section(
    key: str,
    en: str,
    ar: str,
    *,
    tables: list[render.Table] | None = None,
    paras_en: list[str] | None = None,
    paras_ar: list[str] | None = None,
) -> render.Section:
    return render.Section(
        key=key,
        title_en=en,
        title_ar=ar,
        tables=tables or [],
        paragraphs_en=paras_en or [],
        paragraphs_ar=paras_ar or [],
    )
