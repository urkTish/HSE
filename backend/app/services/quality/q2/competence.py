"""Competence (spec 8-quality §C.5, Q-CPT-01…06): requirement rows evaluated through the Phase 2
hook providers — `training_course` (Phase 5) and `personnel_certificate` (Phase 4) with their
in-force predicates — on the user's linked worker. Phase 8 stores no copy of a certificate or a
training record (Q-CPT-02). Registered as `registry.COMPETENCE` for Q1 / Q3 / Q4."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookProviderStatus, HookSubjectType, WorkerStatus
from app.core.enums import AuditAction, Capability, EntityType, Role
from app.core.errors import ErrorCode, not_found
from app.core.quality.common import QProfileScope, profile_allows
from app.core.quality.q2 import (
    QCompetenceAppliesTo,
    QCompetencePolicy,
    QCompetenceState,
    QEvidenceKind,
)
from app.models import Project, User, Worker
from app.models.quality.q2 import QCompetenceCell, QCompetenceReq
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import settings as qs

C = Capability
CA = QCompetenceAppliesTo
P = HookProviderStatus
QUALITY_PEOPLE = (
    Role.qa_qc_manager,
    Role.quality_engineer,
    Role.qc_inspector,
    Role.warehouse_qc,
    Role.responsible_person,
)
# Q-CPT-03 which project roles a requirement's `applies_to` concerns (data defaults; a row may
# also name its people in `filters.user_ids`)
APPLIES_ROLES: dict[str, set[Role]] = {
    CA.ir_inspector: {Role.qc_inspector},
    CA.test_technician: {Role.qc_inspector},
    CA.ndt_technician: {Role.qc_inspector},
    CA.welding_inspector: {Role.qc_inspector},
    CA.receiving_inspector: {Role.warehouse_qc},
    CA.warehouse_qc: {Role.warehouse_qc},
    CA.mapping_lead: {Role.quality_engineer, Role.qa_qc_manager},
    CA.auditor: {Role.qa_qc_manager, Role.quality_engineer},
    CA.calibration_acceptor: {Role.quality_engineer, Role.qa_qc_manager},
    CA.pharmacist: {Role.responsible_person},
    CA.equipment_operator: {Role.qc_inspector, Role.warehouse_qc},
    CA.other: set(QUALITY_PEOPLE),
}
LEVEL = {"1": 1, "2": 2, "3": 3, "I": 1, "II": 2, "III": 3, "basic": 1, "advanced": 2}


@dataclass(frozen=True)
class Q2CompetenceVerdict(reg.CompetenceVerdict):
    """`registry.CompetenceVerdict` with the evidence used and its earliest end (Q-CPT-01)."""

    valid_until: date | None = None
    evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def _at(d: date) -> datetime:
    return datetime.combine(d, time(12, 0), tzinfo=ZoneInfo("Asia/Riyadh"))


def worker_of(db: Session, user_id: uuid.UUID) -> Worker | None:
    return db.scalar(
        select(Worker)
        .where(Worker.user_id == user_id, Worker.status != WorkerStatus.anonymised)
        .order_by(Worker.created_at)
        .limit(1)
    )


def _evidence(db: Session, w: Worker, item: dict[str, Any], at: date) -> dict[str, Any]:
    kind = QEvidenceKind(item["kind"])
    code = str(item["code"])
    when = _at(at)
    if kind == QEvidenceKind.training_course:
        from app.services.train import hook as thook  # noqa: PLC0415

        res = thook.check(db, HookSubjectType.worker, w.id, code, when, None, None)
    else:
        from app.services.cert import providers as cprov  # noqa: PLC0415

        res = cprov.check_personnel(db, w.id, code, when, None, None)
    met = res.status in (P.met, P.expiring)
    lvl_ok = True
    need = item.get("min_level")
    if met and need and kind == QEvidenceKind.personnel_certificate:
        from app.models import PersonnelCertificate  # noqa: PLC0415

        pc = db.scalar(
            select(PersonnelCertificate).where(
                PersonnelCertificate.worker_id == w.id,
                PersonnelCertificate.cert_no == res.ref,
            )
        )
        have = LEVEL.get(pc.level.value, 0) if pc is not None and pc.level is not None else 0
        lvl_ok = have >= LEVEL.get(str(need), int(need) if str(need).isdigit() else 0)
    return {
        "kind": kind.value,
        "code": code,
        "met": met and lvl_ok,
        "valid_until": res.valid_until.isoformat() if res.valid_until else None,
        "ref": res.ref,
        "reason": None
        if met and lvl_ok
        else (res.reason_code or ("LEVEL_TOO_LOW" if not lvl_ok else None)),
    }


def evaluate(db: Session, req: QCompetenceReq, user_id: uuid.UUID, at: date) -> Q2CompetenceVerdict:
    """Q-CPT-01: met ⇔ one `any_of` item met (when the list has items) and every `all_of` item
    met; valid_until = the earliest valid_until of the evidence used."""
    w = worker_of(db, user_id)
    if w is None:
        return Q2CompetenceVerdict(
            False,
            "HOLDER_NOT_LINKED",
            "The user has no linked worker record, so training and certificates cannot be read.",
            "لا يوجد سجل عامل مرتبط بالمستخدم، فلا يمكن قراءة التدريب والشهادات.",
        )
    anys = [_evidence(db, w, x, at) for x in (req.any_of or [])]
    alls = [_evidence(db, w, x, at) for x in (req.all_of or [])]
    any_ok = [x for x in anys if x["met"]]
    met = (not anys or bool(any_ok)) and all(x["met"] for x in alls)
    used = ([min(any_ok, key=lambda x: x["valid_until"] or "9999")] if any_ok else []) + alls
    ends = [date.fromisoformat(x["valid_until"]) for x in used if x["valid_until"]]
    vu = min(ends) if ends and met else None
    if met:
        return Q2CompetenceVerdict(
            True,
            "COMPETENCE_MET",
            f"{req.code} met" + (f" until {vu.isoformat()}." if vu else "."),
            f"المتطلب {req.code} مستوفى" + (f" حتى {vu.isoformat()}." if vu else "."),
            valid_until=vu,
            evidence=tuple(anys + alls),
        )
    return Q2CompetenceVerdict(
        False,
        "COMPETENCE_NOT_MET",
        f"{req.code} is not met on {at.isoformat()}.",
        f"المتطلب {req.code} غير مستوفى في {at.isoformat()}.",
        evidence=tuple(anys + alls),
    )


def get_req(db: Session, code: str) -> QCompetenceReq | None:
    return db.scalar(
        select(QCompetenceReq).where(QCompetenceReq.code == code, QCompetenceReq.active.is_(True))
    )


def check(db: Session, user_id: uuid.UUID, requirement: str, at: date) -> reg.CompetenceVerdict:
    """`registry.COMPETENCE` provider (Q1 IR inspectors, Q3 mapping lead, Q4 auditors)."""
    req = get_req(db, requirement)
    if req is None:
        return reg.CompetenceVerdict(None)
    return evaluate(db, req, user_id, at)


def policy_of(db: Session, project_id: uuid.UUID, req: QCompetenceReq | None) -> str:
    if req is not None and req.policy != QCompetencePolicy.inherit:
        return req.policy.value
    return str(qs.value(db, project_id, "competence_policy") or "warn")


def enforce(
    db: Session,
    project: Project,
    user_id: uuid.UUID,
    requirement: str | None,
    at: date,
    field_name: str,
) -> list[ApiWarning]:
    """Q-CPT-05: policy `block` refuses (422 COMPETENCE_NOT_MET); `warn` returns the warning."""
    if not requirement:
        return []
    req = get_req(db, requirement)
    if req is None:
        return []
    v = evaluate(db, req, user_id, at)
    if v.met:
        return []
    if policy_of(db, project.id, req) == "block":
        raise qc.err(
            422,
            ErrorCode.COMPETENCE_NOT_MET,
            f"{v.detail_en} ({v.code})",
            v.detail_ar,
            requirement=requirement,
            reason=v.code,
        )
    return [
        qc.warning(
            ErrorCode.COMPETENCE_NOT_MET, f"{v.detail_en} ({v.code})", v.detail_ar, field_name
        )
    ]


def by_filter(db: Session, applies: QCompetenceAppliesTo, **flt: str) -> str | None:
    """The first active requirement for a role with matching filters (e.g. NDT method RT)."""
    for r in db.scalars(
        select(QCompetenceReq).where(QCompetenceReq.active.is_(True)).order_by(QCompetenceReq.code)
    ):
        if applies.value not in (r.applies_to or []):
            continue
        f = r.filters or {}
        if all(str(f.get(k, "")).upper() == str(v).upper() for k, v in flt.items() if v):
            return r.code
    return None


# ---- requirements library ----------------------------------------------------------------------


def read(r: QCompetenceReq) -> dict[str, Any]:
    return {
        "id": r.id,
        "code": r.code,
        "title_en": r.title_en,
        "title_ar": r.title_ar,
        "applies_to": list(r.applies_to or []),
        "filters": r.filters or {},
        "any_of": r.any_of or [],
        "all_of": r.all_of or [],
        "policy": r.policy,
        "profile": r.profile,
        "active": r.active,
    }


def _can_read(p: Principal) -> bool:
    if p.is_manager:
        return True
    return any(
        p.grant(a.project_id, C.competence_manage) is not None
        or p.grant(a.project_id, C.quality_view) is not None
        for a in p.active_assignments
        if a.project_id is not None
    )


def _editor(p: Principal) -> None:
    """263 edit: QA/QC Manager and Quality Engineer (the QC inspector and warehouse QC view)."""
    p.ensure_writer()
    if p.is_manager:
        return
    ok = any(
        a.role in (Role.qa_qc_manager, Role.quality_engineer)
        and a.project_id is not None
        and p.grant(a.project_id, C.competence_manage) is not None
        for a in p.active_assignments
    )
    if not ok:
        raise forbidden_error(
            "Editing competence requirements needs a QA/QC Manager or Quality Engineer role."
        )


def list_reqs(db: Session, p: Principal) -> list[dict[str, Any]]:
    if not _can_read(p):
        raise forbidden_error()
    return [read(r) for r in db.scalars(select(QCompetenceReq).order_by(QCompetenceReq.code))]


def _validate(body: dict[str, Any]) -> None:
    for key in ("any_of", "all_of"):
        for i, x in enumerate(body.get(key) or []):
            try:
                QEvidenceKind(x.get("kind"))
            except ValueError as exc:
                raise qc.field_err(
                    f"{key}[{i}].kind", "training_course or personnel_certificate"
                ) from exc
            if not str(x.get("code") or "").strip():
                raise qc.field_err(f"{key}[{i}].code", "Give the course or certificate code.")
    if not (body.get("any_of") or body.get("all_of")):
        raise qc.field_err("any_of", "Name at least one piece of evidence.")
    for a in body.get("applies_to") or []:
        QCompetenceAppliesTo(a)


def create(db: Session, p: Principal, body: dict[str, Any]) -> dict[str, Any]:
    _editor(p)
    _validate(body)
    if db.scalar(select(QCompetenceReq.id).where(QCompetenceReq.code == body["code"])):
        raise qc.field_err("code", "This code is already used.", "الرمز مستخدم.")
    r = QCompetenceReq(
        code=body["code"],
        title_en=body["title_en"],
        title_ar=body.get("title_ar") or "",
        applies_to=list(body.get("applies_to") or []),
        filters=dict(body.get("filters") or {}),
        any_of=list(body.get("any_of") or []),
        all_of=list(body.get("all_of") or []),
        policy=QCompetencePolicy(body.get("policy") or "inherit"),
        profile=QProfileScope(body.get("profile") or "both"),
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    _audit(db, p, r, AuditAction.create, after={"code": r.code})
    refresh_all(db)
    return read(r)


def update(db: Session, p: Principal, req_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    _editor(p)
    r = db.get(QCompetenceReq, req_id)
    if r is None:
        raise not_found("Competence requirement")
    merged = {**read(r), **body}
    _validate(merged)
    before = read(r)
    for k in ("title_en", "title_ar", "applies_to", "filters", "any_of", "all_of", "active"):
        if k in body and body[k] is not None:
            setattr(r, k, body[k])
    if body.get("policy"):
        r.policy = QCompetencePolicy(body["policy"])
    if body.get("profile"):
        r.profile = QProfileScope(body["profile"])
    r.updated_by_user_id = p.user.id
    db.flush()
    b, a = audit.diff(
        {k: str(v) for k, v in before.items()}, {k: str(v) for k, v in read(r).items()}
    )
    _audit(db, p, r, AuditAction.update, before=b, after=a)
    refresh_all(db)
    return read(r)


def _audit(db: Session, p: Principal, r: QCompetenceReq, action: AuditAction, **kw: Any) -> None:
    # org-wide library rows are audited with the Quality settings entity (D-344)
    audit.record(
        db,
        action,
        p.actor(None),
        entity_type=EntityType.q_settings,
        entity_id=r.id,
        details={"competence_requirement": r.code},
        **kw,
    )


def check_api(
    db: Session, p: Principal, project_id: uuid.UUID, user_id: uuid.UUID, code: str, at: date | None
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    if (
        p.grant(project.id, C.competence_manage) is None
        and p.grant(project.id, C.quality_view) is None
    ):
        raise forbidden_error()
    req = get_req(db, code)
    if req is None:
        raise not_found("Competence requirement")
    from app.services.quality.q2 import base  # noqa: PLC0415

    if not base.project_member(db, project, user_id):
        raise qc.field_err(
            "user_id", "The user has no role on this project.", "لا دور لهذا المستخدم في المشروع."
        )
    v = evaluate(db, req, user_id, at or qc.project_day(project))
    return {
        "requirement": code,
        "user_id": user_id,
        "met": v.met,
        "code": v.code,
        "detail_en": v.detail_en,
        "detail_ar": v.detail_ar,
        "valid_until": v.valid_until,
        "evidence": list(v.evidence),
    }


# ---- matrix (Q-CPT-03) and expiry alerts (Q-CPT-04) ------------------------------------------


def _people(db: Session, project: Project) -> dict[uuid.UUID, set[Role]]:
    out: dict[uuid.UUID, set[Role]] = {}
    for role in QUALITY_PEOPLE:
        for a in qc.role_holders(db, project, role):
            out.setdefault(a.user_id, set()).add(role)
    return out


def _applies(r: QCompetenceReq, uid: uuid.UUID, roles: set[Role]) -> bool:
    named = [str(x) for x in (r.filters or {}).get("user_ids") or []]
    if named:
        return str(uid) in named
    return any(roles & APPLIES_ROLES.get(a, set()) for a in r.applies_to or [])


def cells(db: Session, project: Project, on: date) -> list[dict[str, Any]]:
    profile = qc.profile_of(db, project.id)
    reqs = [
        r
        for r in db.scalars(
            select(QCompetenceReq)
            .where(QCompetenceReq.active.is_(True))
            .order_by(QCompetenceReq.code)
        )
        if profile_allows(r.profile, profile)
    ]
    warn_days = int(qs.value(db, project.id, "competence_expiry_warning_days") or 30)
    out = []
    for uid, roles in sorted(_people(db, project).items(), key=lambda x: str(x[0])):
        for r in reqs:
            if not _applies(r, uid, roles):
                out.append(
                    {
                        "user_id": uid,
                        "code": r.code,
                        "state": QCompetenceState.not_applicable,
                        "valid_until": None,
                        "reason": None,
                    }
                )
                continue
            v = evaluate(db, r, uid, on)
            state = QCompetenceState.not_met
            if v.met:
                state = (
                    QCompetenceState.expiring
                    if v.valid_until is not None and (v.valid_until - on).days <= warn_days
                    else QCompetenceState.met
                )
            out.append(
                {
                    "user_id": uid,
                    "code": r.code,
                    "state": state,
                    "valid_until": v.valid_until,
                    "reason": None if v.met else v.code,
                }
            )
    return out


def matrix(
    db: Session, p: Principal, project_id: uuid.UUID, on: date | None = None
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    if p.grant(project.id, C.competence_manage) is None:
        raise forbidden_error()
    day = on or qc.project_day(project)
    cs = cells(db, project, day)
    people = sorted({c["user_id"] for c in cs}, key=str)
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(people)))} if people else {}
    codes = sorted({c["code"] for c in cs})
    reqs = (
        {
            r.code: r
            for r in db.scalars(select(QCompetenceReq).where(QCompetenceReq.code.in_(codes)))
        }
        if codes
        else {}
    )
    return {
        "on": day,
        "requirements": [read(reqs[c]) for c in codes if c in reqs],
        "people": [
            {
                "user_id": uid,
                "full_name_en": users[uid].full_name_en if uid in users else "—",
                "full_name_ar": users[uid].full_name_ar if uid in users else "—",
                "linked_worker": worker_of(db, uid) is not None,
            }
            for uid in people
        ],
        "cells": cs,
        "applicable": sum(1 for c in cs if c["state"] != QCompetenceState.not_applicable),
        "met": sum(
            1 for c in cs if c["state"] in (QCompetenceState.met, QCompetenceState.expiring)
        ),
    }


def expiry_alerts(db: Session, at: datetime) -> int:
    from app.models.quality import QSettings  # noqa: PLC0415

    n = 0
    for s in db.scalars(select(QSettings).where(QSettings.sector_profile.is_not(None))):
        project = db.get(Project, s.project_id)
        if project is None:
            continue
        today = qc.project_day(project, at)
        managers = qc.holders_of(db, project, C.quality_settings)
        for c in cells(db, project, today):
            vu = c["valid_until"]
            if c["state"] not in (QCompetenceState.met, QCompetenceState.expiring) or vu is None:
                continue
            left = (vu - today).days
            mark = 0 if left <= 0 else 7 if left <= 7 else 30 if left <= 30 else None
            if mark is None:
                continue
            n += qc.send(
                db,
                [c["user_id"], *managers],
                f"Competence {c['code']} ends {vu.isoformat()} ({mark}-day notice)",
                f"الكفاءة {c['code']} تنتهي في {vu.isoformat()}",
                project_id=project.id,
                key=f"cpt:{c['user_id']}:{c['code']}:{vu.isoformat()}:{mark}",
                path="/quality/competence",
            )
    return n


# ---- matrix snapshot for the export (Q-CPT-03, dataset quality_competence_matrix) ------------


def refresh_cells(db: Session, project: Project, on: date) -> int:
    """Rebuild the project's `q_competence_cells` from the live evaluation."""
    cs = cells(db, project, on)
    titles = {r.code: r.title_en for r in db.scalars(select(QCompetenceReq))}
    db.execute(delete(QCompetenceCell).where(QCompetenceCell.project_id == project.id))
    for c in cs:
        db.add(
            QCompetenceCell(
                id=uuid.uuid4(),
                project_id=project.id,
                holder_user_id=c["user_id"],
                requirement_code=c["code"],
                requirement_title=titles.get(c["code"], c["code"])[:150],
                state=c["state"],
                valid_until=c["valid_until"],
                reason=(str(c["reason"])[:60] if c["reason"] else None),
                as_of=on,
            )
        )
    db.flush()
    return len(cs)


def _profiled_projects(db: Session) -> list[Project]:
    from app.models.quality import QSettings  # noqa: PLC0415

    out = []
    for s in db.scalars(select(QSettings).where(QSettings.sector_profile.is_not(None))):
        project = db.get(Project, s.project_id)
        if project is not None:
            out.append(project)
    return out


def refresh_all(db: Session, at: datetime | None = None) -> int:
    from app.core.clock import now  # noqa: PLC0415

    n = 0
    for project in _profiled_projects(db):
        n += refresh_cells(db, project, qc.project_day(project, at or now()))
    return n
