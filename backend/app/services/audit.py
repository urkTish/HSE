"""Append-only, hash-chained audit log (spec §3.10, §5.6).

* ``record`` writes an entry in the current transaction.
* ``record(..., defer=True)`` queues an entry that must survive a failed request (e.g.
  ``access_denied``, ``login_failed``); the DB dependency writes queued entries after commit or
  rollback (see ``app.api.deps.get_db``).
* Each entry stores ``hash = SHA-256(prev_hash + canonical entry)``; ``verify_chain`` recomputes.
"""

import hashlib
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import get_settings
from app.core.context import get_request_context
from app.core.enums import AuditAction, AuditResult, EntityType, Role
from app.models import AuditEntry, ProjectSettings

AUDIT_LOCK_KEY = 0x48534541  # "HSEA"
SECRET_KEYS = frozenset({"password", "password_hash", "token", "token_hash", "new_password"})
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        # Phase 1 injured-person identity and medical free text (1-dashboard P1-1)
        "person_name",
        "id_number",
        "id_number_enc",
        "medical_notes",
        "treatments",
        "privacy_reason",
        "date_of_death",
    }
)
MASK = "***"
DEFERRED_KEY = "deferred_audit"

HASHED_FIELDS = (
    "id",
    "seq",
    "occurred_at",
    "actor_user_id",
    "actor_role",
    "on_behalf_project_id",
    "ip_address",
    "user_agent",
    "action",
    "entity_type",
    "entity_id",
    "project_id",
    "before",
    "after",
    "fields_read",
    "details",
    "result",
    "request_id",
)


@dataclass(frozen=True)
class AuditActor:
    user_id: uuid.UUID | None
    role: Role | None = None
    project_id: uuid.UUID | None = None


SYSTEM = AuditActor(None, None)


def _default(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.astimezone(UTC).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, uuid.UUID | set | frozenset):
        return str(v) if isinstance(v, uuid.UUID) else sorted(str(x) for x in v)
    return str(v)


def jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_default, ensure_ascii=False))


def scrub(values: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop secrets, mask sensitive values (rule 35 'before/after')."""
    if values is None:
        return None
    out: dict[str, Any] = {}
    for k, v in values.items():
        if k in SECRET_KEYS:
            continue
        out[k] = MASK if k in SENSITIVE_KEYS and v is not None else v
    result: dict[str, Any] = jsonable(out)
    return result


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Changed fields only."""
    b = jsonable(before)
    a = jsonable(after)
    keys = [k for k in a if b.get(k) != a.get(k)]
    return {k: b.get(k) for k in keys}, {k: a[k] for k in keys}


def _canon_value(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, Enum):
        return v.value
    return v


def canonical(entry: AuditEntry) -> str:
    data = {f: _canon_value(getattr(entry, f)) for f in HASHED_FIELDS}
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str | None, entry: AuditEntry) -> str:
    return hashlib.sha256(((prev_hash or "") + canonical(entry)).encode()).hexdigest()


@contextmanager
def muted(db: Session, *actions: AuditAction) -> Iterator[None]:
    """Within the block, `record` skips these actions on this session: a caller that wraps
    another service and writes the one entry for the whole operation (6g D-225: the export
    registry runs an earlier register exporter and records the export itself)."""
    prev: frozenset[AuditAction] = db.info.get("audit_muted", frozenset())
    db.info["audit_muted"] = prev | set(actions)
    try:
        yield
    finally:
        db.info["audit_muted"] = prev


def record(
    db: Session,
    action: AuditAction,
    actor: AuditActor = SYSTEM,
    *,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    fields_read: list[str] | None = None,
    details: dict[str, Any] | None = None,
    result: AuditResult = AuditResult.success,
    occurred_at: datetime | None = None,
    defer: bool = False,
) -> AuditEntry | None:
    if action in db.info.get("audit_muted", ()):
        return None
    ctx = get_request_context()
    fields: dict[str, Any] = {
        "action": action,
        "actor_user_id": actor.user_id,
        "actor_role": actor.role,
        "on_behalf_project_id": actor.project_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "project_id": project_id,
        "before": scrub(before),
        "after": scrub(after),
        "fields_read": fields_read,
        "details": scrub(details),
        "result": result,
        "occurred_at": (occurred_at or now()).astimezone(UTC),
        "ip_address": ctx.ip_address,
        "user_agent": ctx.user_agent,
        "request_id": ctx.request_id,
    }
    if defer:
        db.info.setdefault(DEFERRED_KEY, []).append(fields)
        return None
    return _insert(db, fields)


def _insert(db: Session, fields: dict[str, Any]) -> AuditEntry:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_LOCK_KEY})
    last = db.execute(
        select(AuditEntry.seq, AuditEntry.hash).order_by(AuditEntry.seq.desc()).limit(1)
    ).first()
    entry = AuditEntry(id=uuid.uuid4(), seq=(last.seq + 1) if last else 1, **fields)
    entry.prev_hash = last.hash if last else None
    entry.hash = compute_hash(entry.prev_hash, entry)
    db.add(entry)
    db.flush()
    return entry


def flush_deferred(db: Session) -> None:
    pending: list[dict[str, Any]] = db.info.pop(DEFERRED_KEY, [])
    for fields in pending:
        _insert(db, fields)


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    checked_count: int
    first_break_seq: int | None
    first_break_entry_id: uuid.UUID | None


def _ranges(seqs: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for n in sorted(seqs):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def _purged_seqs(db: Session) -> list[tuple[int, int]]:
    rows = db.scalars(
        select(AuditEntry.details).where(AuditEntry.action == AuditAction.retention_purge)
    ).all()
    ranges: list[tuple[int, int]] = []
    for d in rows:
        for lo, hi in (d or {}).get("seq_ranges", []):
            ranges.append((int(lo), int(hi)))
    return sorted(ranges)


def _gap_is_purged(lo: int, hi: int, ranges: list[tuple[int, int]]) -> bool:
    """True if every seq in [lo, hi] was removed by a recorded retention purge."""
    pos = lo
    for r_lo, r_hi in ranges:
        if r_hi < pos:
            continue
        if r_lo > pos:
            return False
        pos = r_hi + 1
        if pos > hi:
            return True
    return pos > hi


def verify_chain(db: Session) -> ChainResult:
    """Recompute every hash and check the links (rule 37). Gaps are accepted only where a
    retention_purge entry recorded the removed sequence numbers."""
    purged = _purged_seqs(db)
    prev: AuditEntry | None = None
    count = 0
    stmt = select(AuditEntry).order_by(AuditEntry.seq).execution_options(yield_per=1000)
    for entry in db.scalars(stmt):
        count += 1
        broken = compute_hash(entry.prev_hash, entry) != entry.hash
        prev_seq = prev.seq if prev else 0
        if entry.seq != prev_seq + 1:
            broken = broken or not _gap_is_purged(prev_seq + 1, entry.seq - 1, purged)
        elif (prev is not None and entry.prev_hash != prev.hash) or (
            prev is None and entry.prev_hash is not None
        ):
            broken = True
        if broken:
            return ChainResult(False, count, entry.seq, entry.id)
        prev = entry
    return ChainResult(True, count, None, None)


def _years_ago(ts: datetime, years: int) -> datetime:
    try:
        return ts.replace(year=ts.year - years)
    except ValueError:  # 29 Feb
        return ts.replace(year=ts.year - years, day=28)


def purge_expired(db: Session) -> AuditEntry:
    """Monthly retention purge (rule 40, K5). Writes exactly one retention_purge entry."""
    current = now()
    targets: list[tuple[uuid.UUID | None, int]] = [
        (pid, years)
        for pid, years in db.execute(
            select(ProjectSettings.project_id, ProjectSettings.audit_retention_years)
        ).all()
    ]
    targets.append((None, get_settings().org_audit_retention_years))
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_LOCK_KEY})
    total = 0
    all_seqs: list[int] = []
    lo: datetime | None = None
    hi: datetime | None = None
    per_project: list[dict[str, Any]] = []
    for pid, years in targets:
        cutoff = _years_ago(current, max(1, years))
        all_seqs.extend(
            db.scalars(
                select(AuditEntry.seq).where(
                    AuditEntry.occurred_at < cutoff,
                    AuditEntry.project_id.is_(None)
                    if pid is None
                    else AuditEntry.project_id == pid,
                    AuditEntry.action != AuditAction.retention_purge,
                )
            ).all()
        )
        row = db.execute(
            text("SELECT purged, min_occurred, max_occurred FROM hse_audit_purge(:p, :c)"),
            {"p": pid, "c": cutoff},
        ).one()
        if row.purged:
            total += row.purged
            lo = row.min_occurred if lo is None else min(lo, row.min_occurred)
            hi = row.max_occurred if hi is None else max(hi, row.max_occurred)
            per_project.append(
                {"project_id": pid, "count": row.purged, "cutoff": cutoff, "years": years}
            )
    entry = record(
        db,
        AuditAction.retention_purge,
        entity_type=EntityType.audit_log,
        details={
            "count": total,
            "from": lo,
            "to": hi,
            "by_project": per_project,
            "seq_ranges": _ranges(all_seqs),
        },
    )
    assert entry is not None  # noqa: S101
    return entry
