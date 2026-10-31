"""Q0 HTTP routes: Quality settings and profile, schema, reference lists, positions, the
responsible-person matrix and re-assignment, numbering, home and "Awaiting my sign-off", links
and sign-offs (spec 8-quality §A.2–§A.5, §A.8.5, §A.8.6, §A.12)."""

import uuid
from typing import Any

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses
from app.core.quality.common import (
    DEFAULT_POSITIONS,
    LABELS,
    RECORD_TYPES,
    QRecordType,
)
from app.schemas.quality.q0 import (
    QAwaitingRead,
    QHolderCreate,
    QHolderEnd,
    QHomeRead,
    QLinkCreate,
    QLinkRead,
    QNumberingRead,
    QNumberingUpdate,
    QPositionCreate,
    QPositionRead,
    QPositionUpdate,
    QProfileSet,
    QReassign,
    QRecordTypeRead,
    QReference,
    QRpRuleCreate,
    QRpRuleRead,
    QRpRuleUpdate,
    QSettingDefRead,
    QSettingsRead,
    QSettingsUpdate,
    QSignoffRead,
)
from app.services.quality import common as qc
from app.services.quality import home, links, numbering, rpm, signoff
from app.services.quality import settings as qs

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/quality/reference",
    response_model=QReference,
    summary="Quality lists, record types and steps with EN / AR labels",
    responses=error_responses(401),
)
def q_reference(user: CurrentUser) -> QReference:
    rts = [
        QRecordTypeRead(
            code=d.code,
            part=d.part,
            profile=d.profile,
            prefix=d.prefix,
            en=d.en,
            ar=d.ar,
            steps=[
                {
                    "code": s.code,
                    "capability": s.capability.value,
                    "en": s.en,
                    "ar": s.ar,
                    "decisions": list(s.decisions),
                }
                for s in d.steps
            ],
        )
        for d in RECORD_TYPES.values()
    ]
    labels = {k: {v: [en, ar] for v, (en, ar) in vals.items()} for k, vals in LABELS.items()}
    pos = [
        {"code": c, "name_en": en, "name_ar": ar, "profile": p.value}
        for c, en, ar, p in DEFAULT_POSITIONS
    ]
    return QReference(record_types=rts, labels=labels, positions_default=pos)


@router.get(
    "/quality/settings/schema",
    response_model=list[QSettingDefRead],
    summary="Settings registry of every part (Q-SET-01)",
    responses=error_responses(401),
)
def q_settings_schema(user: CurrentUser) -> list[dict[str, Any]]:
    return qs.schema()


@router.get(
    "/projects/{project_id}/quality/settings",
    response_model=QSettingsRead,
    summary="Quality settings of a project (238 / 239)",
    responses=E,
)
def q_get_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return qs.read(db, user, project_id)


@router.patch(
    "/projects/{project_id}/quality/settings",
    response_model=QSettingsRead,
    summary="Change settings (239); out of range → 422 SETTING_OUT_OF_RANGE",
    responses=E,
)
def q_update_settings(
    project_id: uuid.UUID, body: QSettingsUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return qs.patch(
        db, user, project_id, body.values, body.quality_start_date, body.clear_quality_start_date
    )


@router.put(
    "/projects/{project_id}/quality/profile",
    response_model=QSettingsRead,
    summary="Set (Q-PRF-01) or change (Q-PRF-03, reason ≥ 20) the sector profile (239)",
    responses=E,
)
def q_set_profile(
    project_id: uuid.UUID, body: QProfileSet, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return qs.set_profile(
        db, user, project_id, body.sector_profile, body.reason, body.quality_start_date
    )


@router.get(
    "/projects/{project_id}/quality/home",
    response_model=QHomeRead,
    summary="Quality home (profile-aware)",
    responses=E,
)
def q_home(project_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return home.home(db, user, project_id)


@router.get(
    "/projects/{project_id}/quality/awaiting",
    response_model=QAwaitingRead,
    summary="Awaiting my sign-off across all parts, oldest first (Q-RPM-11)",
    responses=E,
)
def q_awaiting(project_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return home.awaiting(db, user, project_id)


# ---- positions -----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/positions",
    response_model=list[QPositionRead],
    summary="Positions and holders (§A.4.1)",
    responses=E,
)
def q_list_positions(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return rpm.list_positions(db, user, project_id)


@router.post(
    "/projects/{project_id}/quality/positions",
    response_model=QPositionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a position (239)",
    responses=E,
)
def q_create_position(
    project_id: uuid.UUID, body: QPositionCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return rpm.create_position(db, user, project_id, body.model_dump())


@router.patch(
    "/quality/positions/{position_id}",
    response_model=QPositionRead,
    summary="Edit a position (239)",
    responses=E,
)
def q_update_position(
    position_id: uuid.UUID, body: QPositionUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return rpm.update_position(db, user, position_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/positions/{position_id}/holders",
    response_model=QPositionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a holder (239)",
    responses=E,
)
def q_add_holder(
    position_id: uuid.UUID, body: QHolderCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return rpm.add_holder(db, user, position_id, body.model_dump())


@router.post(
    "/quality/position-holders/{holder_id}/end",
    response_model=QPositionRead,
    summary="End a holder (239)",
    responses=E,
)
def q_end_holder(
    holder_id: uuid.UUID, body: QHolderEnd, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return rpm.end_holder(db, user, holder_id, body.valid_to)


# ---- matrix --------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/rp-rules",
    response_model=list[QRpRuleRead],
    summary="Responsible-person matrix (§A.4.3)",
    responses=E,
)
def q_list_rp_rules(
    project_id: uuid.UUID, user: CurrentUser, db: DB, record_type: QRecordType | None = None
) -> list[dict[str, Any]]:
    return rpm.list_rules(db, user, project_id, record_type.value if record_type else None)


@router.post(
    "/projects/{project_id}/quality/rp-rules",
    response_model=QRpRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a matrix row (239); replaces the active row of the same type, step and qualifier",
    responses=E,
)
def q_create_rp_rule(
    project_id: uuid.UUID, body: QRpRuleCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return rpm.create_rule(db, user, project_id, body.model_dump())


@router.patch(
    "/quality/rp-rules/{rule_id}",
    response_model=QRpRuleRead,
    summary="Change a matrix row (239; applies to steps not yet signed, Q-RPM-10)",
    responses=E,
)
def q_update_rp_rule(
    rule_id: uuid.UUID, body: QRpRuleUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return rpm.update_rule(db, user, rule_id, body.model_dump(exclude_unset=True))


@router.post(
    "/projects/{project_id}/quality/reassign",
    response_model=QRpRuleRead,
    summary="Re-assign one pending step on one record (Q-RPM-09)",
    responses=E,
)
def q_reassign_step(
    project_id: uuid.UUID, body: QReassign, user: CurrentUser, db: DB
) -> dict[str, Any]:
    project = qc.get_project(db, user, project_id)
    r = rpm.reassign(
        db,
        user,
        project,
        body.record_type,
        body.record_id,
        body.step,
        body.assignee_kind,
        body.assignee,
        body.reason,
    )
    return rpm.rule_read(r)


# ---- numbering -----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/numbering",
    response_model=list[QNumberingRead],
    summary="Number formats per record type (Q-NUM-01)",
    responses=E,
)
def q_list_numbering(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return numbering.list_formats(db, user, project_id)


@router.put(
    "/projects/{project_id}/quality/numbering/{record_type}",
    response_model=QNumberingRead,
    summary="Change a format (239; 422 NUMBER_FORMAT_INVALID; new numbers only)",
    responses=E,
)
def q_update_numbering(
    project_id: uuid.UUID,
    record_type: QRecordType,
    body: QNumberingUpdate,
    user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    return numbering.update_format(db, user, project_id, record_type, body.format, body.reset)


# ---- links and sign-offs ------------------------------------------------------------------------


@router.get(
    "/quality/links",
    response_model=list[QLinkRead],
    summary="Links of a Quality record (§A.8.5)",
    responses=E,
)
def q_list_links(
    record_type: QRecordType, record_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    return links.list_api(db, user, record_type, record_id)


@router.post(
    "/quality/links",
    response_model=QLinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Link two records of the same project (422 LINK_NOT_ALLOWED)",
    responses=E,
)
def q_create_link(body: QLinkCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return links.create(db, user, body.from_type, body.from_id, body.to_type, body.to_id, body.kind)


@router.get(
    "/quality/signoffs",
    response_model=list[QSignoffRead],
    summary="Sign-offs of a record (append-only; no update or delete route, Q-RPM-05)",
    responses=E,
)
def q_list_signoffs(
    record_type: QRecordType, record_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    links.list_api(db, user, record_type, record_id)  # visibility of the record
    from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

    rows = signoff.signoffs_for(db, record_type, record_id)
    if rows and read_only_viewer(user, rows[0].project_id):
        return []
    return [signoff.read(db, s) for s in rows]
