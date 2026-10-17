"""Administrator delete of any record, kept traceable in ``deleted_records`` (D-271).

The record and everything that cannot exist without it are removed by the same foreign-key walk
as the project delete (``project_purge``); optional links from other records are cleared. A copy
of every deleted row is stored when the delete is small (``SNAPSHOT_LIMIT`` rows), otherwise the
root row and the row counts per table. Users are excluded: accounts are deactivated, never
deleted, because the audit trail points at them.
"""

import uuid
from functools import lru_cache
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import project_deleters
from app.core.enums import AuditAction, EntityType
from app.core.errors import not_found, validation_error
from app.db.base import Base
from app.models import DeletedRecord
from app.services import audit
from app.services.permissions import Principal, forbidden_error
from app.services.project_purge import purge

SNAPSHOT_LIMIT = 5000
LABEL_COLUMNS = (
    "ref",
    "code",
    "permit_no",
    "audit_no",
    "case_no",
    "application_no",
    "wap_no",
    "adp_no",
    "avp_no",
    "certificate_no",
    "title",
    "name_en",
    "full_name_en",
    "short_code",
)
# Entity types whose table name does not follow the plural of the type.
TABLES = {
    "adp": "airside_driving_permits",
    "avp": "airside_vehicle_permits",
    "wap": "work_area_permits",
    "spill": "env_spills",
    "water_entry": "env_water_entries",
    "discharge_day": "env_discharge_days",
    "background_declaration": "env_background_declarations",
    "lesson": "fu_lessons",
    "lesson_link": "fu_lesson_links",
    "lesson_effectiveness": "fu_effectiveness_checks",
    "followup_rule": "fu_rules",
    "followup_requirement": "fu_requirements",
    "followup_pack": "fu_packs",
    "scorecard": "sc_cards",
    "scorecard_profile": "sc_profiles",
    "scorecard_remark": "sc_remarks",
    "watch_list_entry": "sc_watch_entries",
    "report_pack": "rp_packs",
    "export_job": "xp_jobs",
    "export_subscription": "xp_subscriptions",
    "erp": "emergency_erps",
    "assembly_point": "emergency_assembly_points",
    "rescue_team": "emergency_rescue_teams",
    "muster_device": "emergency_muster_devices",
    "rest_station": "heat_rest_stations",
    "monitoring_point": "heat_monitoring_points",
    "ban_patrol": "heat_ban_patrols",
    "ban_exemption": "heat_ban_exemptions",
    "bump_test": "gas_bump_tests",
}
EXCLUDED = frozenset({"user"})


@lru_cache
def deletable_tables() -> dict[str, str]:
    """Entity type → table for every record type an administrator can delete."""
    tables = Base.metadata.tables
    out: dict[str, str] = {}
    for e in EntityType:
        v = e.value
        if v in EXCLUDED:
            continue
        candidates = [TABLES.get(v), f"{v}s", f"{v}es", v]
        if v.endswith("y"):
            candidates.append(f"{v[:-1]}ies")
        for name in candidates:
            if name and name in tables and "id" in tables[name].c:
                out[v] = name
                break
    return out


def is_admin(p: Principal) -> bool:
    return p.user.email.lower() in project_deleters()


def require_admin(p: Principal) -> None:
    if not is_admin(p):
        raise forbidden_error("Only the platform administrator can delete records.")


def _label(entity_type: str, row: dict[str, Any]) -> str:
    for col in LABEL_COLUMNS:
        v = row.get(col)
        if v:
            return f"{entity_type} {v}"[:300]
    return f"{entity_type} {row.get('id')}"[:300]


def delete_record(
    db: Session, p: Principal, entity_type: str, entity_id: uuid.UUID, reason: str
) -> DeletedRecord:
    require_admin(p)
    table = deletable_tables().get(entity_type)
    if table is None:
        raise validation_error("entity_type", "This kind of record cannot be deleted here.")
    if not reason.strip():
        raise validation_error("reason", "Give a reason for the delete.")
    row = db.scalar(
        # table comes from deletable_tables(), i.e. the model metadata, never from the caller
        text(f'SELECT row_to_json(x)::jsonb FROM "{table}" x WHERE x.id = :id'),  # noqa: S608
        {"id": entity_id},
    )
    if row is None:
        raise not_found("Record")
    project_id = row.get("project_id") if table != "projects" else row.get("id")
    result = purge(db, table, entity_id, snapshot_limit=SNAPSHOT_LIMIT)
    rec = DeletedRecord(
        deleted_by_user_id=p.user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=uuid.UUID(str(project_id)) if project_id else None,
        label=_label(entity_type, row),
        reason=reason.strip()[:500],
        row_counts=result.deleted,
        rows=result.rows if result.rows is not None else {table: [row]},
    )
    db.add(rec)
    db.flush()
    audit.record(
        db,
        AuditAction.archive,
        p.actor(None),
        entity_type=EntityType(entity_type),
        entity_id=entity_id,
        before=row if len(str(row)) < 20_000 else {"id": str(entity_id)},
        details={"deleted": True, "rows_deleted": result.deleted, "deleted_record_id": str(rec.id)},
    )
    return rec


def list_deleted(
    db: Session, p: Principal, page: int, page_size: int
) -> tuple[list[DeletedRecord], int]:
    require_admin(p)
    total = db.scalar(select(func.count()).select_from(DeletedRecord)) or 0
    rows = db.scalars(
        select(DeletedRecord)
        .order_by(DeletedRecord.deleted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


def get_deleted(db: Session, p: Principal, record_id: uuid.UUID) -> DeletedRecord:
    require_admin(p)
    rec = db.get(DeletedRecord, record_id)
    if rec is None:
        raise not_found("Deleted record")
    return rec
