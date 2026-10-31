"""Record numbering (spec 8-quality §A.5, Q-NUM-01…04).

Formats are data (`q_numbering`, one row per project and record type, defaults from
`app.core.quality.common.default_numbering`). A number is assigned when a record leaves Draft, from
a counter in that row locked FOR UPDATE (the project row is locked first, `hse_common.next_seq`
pattern), so two submissions never get the same number and numbers are never reused."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode
from app.core.quality.common import RECORD_TYPES, QNumberReset, QRecordType, default_numbering
from app.models import Project
from app.models.quality import QNumbering
from app.services import audit
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc

TOKEN = re.compile(r"\{(PFX|PROJECT|SITE|DISC|YYYY|YY|SEQ[3-6])\}")
LITERAL = re.compile(r"[A-Za-z0-9\-/_]*")
MAX_LEN = 40


def invalid(why: str) -> Any:
    return qc.err(
        422,
        ErrorCode.NUMBER_FORMAT_INVALID,
        f"Invalid number format: {why}",
        "صيغة الترقيم غير صالحة.",
    )


def validate_format(fmt: str, reset: QNumberReset) -> None:
    """Q-NUM-02: one {SEQn}; {YYYY} or {YY} when the reset is yearly; only tokens and literal
    letters, digits, `-`, `/`, `_`."""
    seqs = re.findall(r"\{SEQ[3-6]\}", fmt)
    if len(seqs) != 1:
        raise invalid("exactly one {SEQ3}…{SEQ6} token is required")
    if reset == QNumberReset.yearly and "{YYYY}" not in fmt and "{YY}" not in fmt:
        raise invalid("a yearly reset needs {YYYY} or {YY}")
    rest = TOKEN.sub("", fmt)
    if not LITERAL.fullmatch(rest):
        raise invalid("unknown token or character")
    if len(render(fmt, "PFX", "A" * 12, "SITE", "DISC", 2026, 1)) > MAX_LEN:
        raise invalid(f"the rendered number would exceed {MAX_LEN} characters")


def render(
    fmt: str, pfx: str, project_code: str, site: str | None, disc: str | None, year: int, seq: int
) -> str:
    def sub(m: re.Match[str]) -> str:
        t = m.group(1)
        if t == "PFX":
            return pfx
        if t == "PROJECT":
            return project_code
        if t == "SITE":
            return site or "SITE"
        if t == "DISC":
            return disc or "GEN"
        if t == "YYYY":
            return f"{year:04d}"
        if t == "YY":
            return f"{year % 100:02d}"
        return f"{seq:0{int(t[3:])}d}"

    return TOKEN.sub(sub, fmt)


def _row(db: Session, project_id: uuid.UUID, rt: QRecordType, lock: bool) -> QNumbering:
    fmt, reset = default_numbering(rt)
    db.execute(
        insert(QNumbering)
        .values(
            id=uuid.uuid4(),
            project_id=project_id,
            record_type=rt.value,
            format=fmt,
            reset=reset.value,
            counters={},
        )
        .on_conflict_do_nothing(index_elements=["project_id", "record_type"])
    )
    stmt = select(QNumbering).where(
        QNumbering.project_id == project_id, QNumbering.record_type == rt.value
    )
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt.execution_options(populate_existing=True))
    assert row is not None  # noqa: S101
    return row


def assign(
    db: Session,
    project: Project,
    rt: QRecordType,
    *,
    on: date | None = None,
    site_code: str | None = None,
    disc: str | None = None,
    pfx: str | None = None,
) -> str:
    """Next number for a record leaving Draft (Q-NUM-03)."""
    db.execute(select(Project.id).where(Project.id == project.id).with_for_update())
    row = _row(db, project.id, rt, lock=True)
    day = on or qc.project_day(project)
    prefix = pfx or RECORD_TYPES[rt].prefix
    period = str(day.year) if row.reset == QNumberReset.yearly else "all"
    key = f"{period}|{disc or ''}|{prefix}"
    counters = dict(row.counters or {})
    seq = int(counters.get(key, 0)) + 1
    counters[key] = seq
    row.counters = counters
    db.flush()
    return render(row.format, prefix, project.code, site_code, disc, day.year, seq)


def bump_to(
    db: Session, project: Project, rt: QRecordType, year: int, seq: int, disc: str = ""
) -> None:
    """Seeds: make sure the counter is at least `seq` (numbers already used are never reused)."""
    row = _row(db, project.id, rt, lock=True)
    prefix = RECORD_TYPES[rt].prefix
    period = str(year) if row.reset == QNumberReset.yearly else "all"
    key = f"{period}|{disc}|{prefix}"
    counters = dict(row.counters or {})
    counters[key] = max(int(counters.get(key, 0)), seq)
    row.counters = counters
    db.flush()


def _read(project: Project, row: QNumbering) -> dict[str, Any]:
    d = RECORD_TYPES[QRecordType(row.record_type)]
    day = qc.project_day(project)
    return {
        "record_type": row.record_type,
        "prefix": d.prefix,
        "format": row.format,
        "reset": row.reset,
        "preview": render(row.format, d.prefix, project.code, "S-01", "STC", day.year, 1),
        "part": d.part,
        "profile": d.profile,
    }


def list_formats(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    if (
        p.grant(project.id, Capability.quality_view) is None
        and p.grant(project.id, Capability.quality_settings) is None
    ):
        raise forbidden_error()
    have = {
        r.record_type: r
        for r in db.scalars(select(QNumbering).where(QNumbering.project_id == project.id))
    }
    out = []
    for rt, d in RECORD_TYPES.items():
        if not d.numbered:
            continue
        row = have.get(rt.value)
        if row is None:
            fmt, reset = default_numbering(rt)
            row = QNumbering(project_id=project.id, record_type=rt.value, format=fmt, reset=reset)
        out.append(_read(project, row))
    return out


def update_format(
    db: Session, p: Principal, project_id: uuid.UUID, rt: QRecordType, fmt: str, reset: QNumberReset
) -> dict[str, Any]:
    """Q-NUM-04: applies to numbers assigned after it; existing numbers never change."""
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    p.require(project.id, Capability.quality_settings)
    fmt = fmt.strip()
    validate_format(fmt, reset)
    row = _row(db, project.id, rt, lock=True)
    before = {"format": row.format, "reset": row.reset}
    row.format = fmt
    row.reset = reset
    row.updated_at = now()
    row.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(project.id),
        entity_type=EntityType.q_numbering,
        entity_id=row.id,
        project_id=project.id,
        before=before,
        after={"format": fmt, "reset": reset, "record_type": rt.value},
    )
    return _read(project, row)
