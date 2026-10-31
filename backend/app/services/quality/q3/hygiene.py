"""Hygiene, cleaning and pest control (spec 8-quality §D.6, Q-HYG-01…04): check schedules with
due checks computed on read (as DECISIONS #157; weeks run Sunday–Saturday), hygiene checks on
the 6d engine (`QHYG`, owner `q_hygiene`), pest stations and pest-control visits with the
"not serviced" warning and the activity-trend proposals."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, Role
from app.core.field_enums import ResponseOwnerType
from app.core.quality.common import QDetectionStage, QNcrClass, QRecordType
from app.core.quality.q3 import (
    QCheckFrequency,
    QCheckType,
    QPestActivity,
    QPestStationType,
    QStorageClass,
)
from app.models import Project, RoleAssignment, Zone
from app.models.field import ChecklistResponse
from app.models.quality.q3 import QCheckSchedule, QPestStation, QPestVisit, QStorageZone
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality.q3 import base as b
from app.services.quality.q3 import checklists

C = Capability
RT = QRecordType.excursion  # audit entity for the hygiene registers (no QRT type of their own)
COLD = frozenset({QStorageClass.chilled, QStorageClass.frozen, QStorageClass.pharma_2_8})


# ---- schedules and due checks (Q-HYG-01) ---------------------------------------------------------


def periods(s: QCheckSchedule, until: date) -> list[tuple[date, date]]:
    """Periods [start, end] from the schedule's start date up to `until`."""
    out: list[tuple[date, date]] = []
    d = s.start_date
    if s.frequency == QCheckFrequency.daily:
        while d <= until:
            out.append((d, d))
            d += timedelta(days=1)
    elif s.frequency == QCheckFrequency.weekly:
        d = d - timedelta(days=(d.weekday() + 1) % 7)  # back to Sunday
        while d <= until:
            out.append((d, d + timedelta(days=6)))
            d += timedelta(days=7)
    elif s.frequency == QCheckFrequency.fortnightly:
        while d <= until:
            out.append((d, d + timedelta(days=13)))
            d += timedelta(days=14)
    else:
        d = d.replace(day=1)
        while d <= until:
            nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
            out.append((d, nxt - timedelta(days=1)))
            d = nxt
    return out


def done_dates(db: Session, s: QCheckSchedule, a: date, e: date) -> list[date]:
    if s.check_type == QCheckType.hygiene:
        q = select(ChecklistResponse.completed_date).where(
            ChecklistResponse.project_id == s.project_id,
            ChecklistResponse.owner_type == ResponseOwnerType.q_hygiene,
            ChecklistResponse.template_code == s.template_code,
            ChecklistResponse.voided.is_(False),
            ChecklistResponse.completed_date >= a,
            ChecklistResponse.completed_date <= e,
        )
        q = (
            q.where(ChecklistResponse.zone_id == s.zone_id)
            if s.zone_id
            else q.where(ChecklistResponse.site_id == s.site_id)
        )
        return [x for x in db.scalars(q) if x]
    rows = db.scalars(
        select(QPestVisit.visited_at).where(
            QPestVisit.project_id == s.project_id,
            QPestVisit.site_id == s.site_id,
            QPestVisit.visited_at >= b.day_start(a),
            QPestVisit.visited_at < b.day_start(e + timedelta(days=1)),
        )
    )
    return [b.local_day(x) for x in rows]


def due_status(
    db: Session, s: QCheckSchedule, today: date, a: date | None = None, e: date | None = None
) -> list[dict[str, Any]]:
    """Each period: done (a response in the period), due (current) or overdue (ended, not done)."""
    out = []
    for pa, pe in periods(s, today):
        if (a and pe < a) or (e and pa > e):
            continue
        done = bool(done_dates(db, s, pa, pe))
        out.append(
            {
                "from": pa,
                "to": pe,
                "status": "done" if done else ("due" if pe >= today else "overdue"),
            }
        )
    return out


def compliance(db: Session, project: Project, a: date, e: date, as_of: date) -> tuple[int, int]:
    """K-168: (done in their period, due checks whose period ended in [a, e] and ≤ as_of)."""
    done = total = 0
    for s in db.scalars(
        select(QCheckSchedule).where(
            QCheckSchedule.project_id == project.id, QCheckSchedule.active.is_(True)
        )
    ):
        for pa, pe in periods(s, min(e, as_of)):
            if pe < a or pe > e or pe > as_of:
                continue
            total += 1
            done += bool(done_dates(db, s, pa, pe))
    return done, total


def schedule_read(db: Session, s: QCheckSchedule, today: date) -> dict[str, Any]:
    recent = due_status(db, s, today, today - timedelta(days=62), today)
    return {
        "id": s.id,
        "site": b.site_ref(db, s.site_id),
        "zone": b.zone_ref(db, s.zone_id),
        "check_type": s.check_type,
        "template_code": s.template_code,
        "frequency": s.frequency,
        "weekday": s.weekday,
        "start_date": s.start_date,
        "assignee_role": s.assignee_role,
        "active": s.active,
        "current": next((x for x in reversed(recent) if x["status"] == "due"), None),
        "overdue": [x for x in recent if x["status"] == "overdue"],
        "recent": recent[-8:],
    }


def list_schedules(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    today = qc.project_day(project)
    return [
        schedule_read(db, s, today)
        for s in db.scalars(
            select(QCheckSchedule)
            .where(QCheckSchedule.project_id == project.id)
            .order_by(QCheckSchedule.created_at)
        )
        if g.scope.value == "responsible" or g.covers_site(s.site_id)
    ]


def create_schedule(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(
        db, p, project_id, QRecordType.mapping_study, C.storage_manage
    )
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    if body.get("zone_id"):
        b.zone_of(db, project, body["zone_id"])
    ct = QCheckType(body["check_type"])
    t = checklists.template(db, ct.value, body.get("template_code"))
    role = body.get("assignee_role") or Role.warehouse_qc.value
    Role(role)
    fr = QCheckFrequency(body["frequency"])
    s = QCheckSchedule(
        project_id=project.id,
        site_id=site.id,
        zone_id=body.get("zone_id"),
        check_type=ct,
        template_code=t.template_code,
        frequency=fr,
        weekday=body.get("weekday"),
        start_date=body.get("start_date") or qc.project_day(project),
        assignee_role=role,
        active=True,
        created_by_user_id=p.user.id,
    )
    db.add(s)
    db.flush()
    return schedule_read(db, s, qc.project_day(project))


def update_schedule(
    db: Session, p: Principal, sid: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    s = db.get(QCheckSchedule, sid)
    if s is None or not p.can_see_project(s.project_id):
        raise b.not_found(db, p, RT, sid, None)
    project, g = b.project_for_progress(db, p, s.project_id, C.storage_manage)
    b.require_site(g, s.site_id)
    for k in ("weekday", "assignee_role", "active"):
        if k in body and body[k] is not None:
            setattr(s, k, body[k])
    if body.get("frequency"):
        s.frequency = QCheckFrequency(body["frequency"])
    return schedule_read(db, s, qc.project_day(project))


def run_check(db: Session, p: Principal, sid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """A hygiene check on the 6d runner; a critical failure proposes an NCR (source
    `hygiene_pest`) and a hold of the affected stock (Q-HYG-02)."""
    s = db.get(QCheckSchedule, sid)
    if s is None or not p.can_see_project(s.project_id):
        raise b.not_found(db, p, RT, sid, None)
    project, g = b.project_for_create(
        db, p, s.project_id, QRecordType.mapping_study, C.storage_manage
    )
    b.require_site(g, s.site_id)
    if s.check_type != QCheckType.hygiene:
        raise qc.field_err(
            "check_type", "Pest visits are recorded as visits.", "تُسجل زيارات الآفات كزيارات."
        )
    out = checklists.respond(
        db,
        p.user.id,
        project,
        ResponseOwnerType.q_hygiene,
        "hygiene",
        s.site_id,
        body["answers"],
        zone_id=s.zone_id,
        code=s.template_code,
        completed_at=body.get("completed_at"),
    )
    proposals = []
    if out.critical_failures:
        proposals = [
            {
                "kind": "ncr",
                "source_type": "hygiene_pest",
                "source_id": out.response.id,
                "items": out.critical_failures,
            },
            {"kind": "hold", "reason": "pest_hygiene", "zone_id": s.zone_id},
        ]
    return {
        "response": checklists.response_read(out.response),
        "passed": out.passed,
        "proposals": proposals,
    }


# ---- pest stations and visits (Q-HYG-03, -04) ----------------------------------------------------


def station_read(db: Session, st: QPestStation) -> dict[str, Any]:
    return {
        "id": st.id,
        "code": st.code,
        "site_id": st.site_id,
        "zone": b.zone_ref(db, st.zone_id),
        "station_type": st.station_type,
        "location_note": st.location_note,
        "provider": b.supplier_ref(db, st.provider_supplier_id),
        "activity_trend": st.activity_trend,
        "active": st.active,
    }


def list_stations(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    return [
        station_read(db, x)
        for x in db.scalars(
            select(QPestStation)
            .where(QPestStation.project_id == project.id)
            .order_by(QPestStation.code)
        )
    ]


def create_station(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(
        db, p, project_id, QRecordType.mapping_study, C.storage_manage
    )
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    code = body["code"].strip().upper()
    if db.scalar(
        select(QPestStation.id).where(QPestStation.site_id == site.id, QPestStation.code == code)
    ):
        raise qc.field_err(
            "code", "This station code is used on the site.", "رمز المحطة مستخدم في الموقع."
        )
    st = QPestStation(
        project_id=project.id,
        site_id=site.id,
        zone_id=body.get("zone_id"),
        code=code,
        station_type=QPestStationType(body["station_type"]),
        location_note=body.get("location_note"),
        provider_supplier_id=body.get("provider_supplier_id"),
        active=True,
        created_by_user_id=p.user.id,
    )
    db.add(st)
    db.flush()
    return station_read(db, st)


def _visit_no(db: Session, project: Project, at: datetime) -> str:
    db.execute(select(Project.id).where(Project.id == project.id).with_for_update())
    year = b.local_day(at).year
    n = len(
        list(
            db.scalars(
                select(QPestVisit.id).where(
                    QPestVisit.project_id == project.id,
                    QPestVisit.visit_no.like(f"PSV-{project.code}-{year}-%"),
                )
            )
        )
    )
    return f"PSV-{project.code}-{year}-{n + 1:04d}"


def record_visit(
    db: Session, project: Project, user_id: uuid.UUID | None, body: dict[str, Any]
) -> tuple[QPestVisit, list[Any], list[dict[str, Any]]]:
    site_id = body["site_id"]
    at: datetime = body.get("visited_at") or now()
    stations = {
        x.id: x
        for x in db.scalars(
            select(QPestStation).where(
                QPestStation.site_id == site_id, QPestStation.active.is_(True)
            )
        )
    }
    results = []
    for r in body.get("station_results") or []:
        sid = uuid.UUID(str(r["station_id"]))
        if sid not in stations:
            raise qc.field_err(
                "station_results",
                "A station is not active on this site.",
                "محطة غير نشطة في الموقع.",
            )
        results.append(
            {
                "station_id": str(sid),
                "activity": QPestActivity(r.get("activity") or "none").value,
                "pest_type": r.get("pest_type"),
                "bait_consumed_pct": r.get("bait_consumed_pct"),
                "action": r.get("action"),
            }
        )
    seen = {r["station_id"] for r in results}
    missing = [st.code for sid, st in stations.items() if str(sid) not in seen]
    v = QPestVisit(
        project_id=project.id,
        visit_no=_visit_no(db, project, at),
        site_id=site_id,
        provider_supplier_id=body.get("provider_supplier_id"),
        visited_at=at,
        technician_name=body.get("technician_name"),
        chemicals=body.get("chemicals") or [],
        station_results=results,
        not_serviced=missing,
        proposals=[],
        created_by_user_id=user_id,
    )
    db.add(v)
    db.flush()
    warnings = []
    if missing:
        warnings.append(
            qc.warning(
                "STATION_NOT_SERVICED",
                f"Stations not in this visit: {', '.join(missing)} (Q-HYG-04).",
                f"محطات لم تُخدم في هذه الزيارة: {', '.join(missing)}.",
                "station_results",
            )
        )
    proposals = []
    prev = db.scalar(
        select(QPestVisit)
        .where(QPestVisit.site_id == site_id, QPestVisit.visited_at < at, QPestVisit.id != v.id)
        .order_by(QPestVisit.visited_at.desc())
        .limit(1)
    )
    prev_active = {
        r["station_id"] for r in (prev.station_results if prev else []) if r["activity"] != "none"
    }
    for r in results:
        if r["activity"] == "none":
            continue
        st = stations[uuid.UUID(r["station_id"])]
        sz = db.get(QStorageZone, st.zone_id) if st.zone_id else None
        why = []
        if r["station_id"] in prev_active:
            why.append("activity on 2 consecutive visits")
        if r["activity"] == "high":
            why.append("high activity")
        if sz is not None and sz.storage_class in COLD:
            why.append(f"activity in a {sz.storage_class.value} zone")
        if why:
            st.activity_trend = True
            proposals.append(
                {
                    "station": st.code,
                    "station_id": st.id,
                    "why": why,
                    "kinds": ["quality_alert", "ncr"],
                    "source_type": "hygiene_pest",
                    "source_id": v.id,
                }
            )
    v.proposals = [
        {**x, "station_id": str(x["station_id"]), "source_id": str(x["source_id"])}
        for x in proposals
    ]
    return v, warnings, proposals


def create_visit(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(
        db, p, project_id, QRecordType.mapping_study, C.storage_manage
    )
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    v, warnings, _ = record_visit(db, project, p.user.id, body)
    if body.get("answers"):
        out = checklists.respond(
            db,
            p.user.id,
            project,
            ResponseOwnerType.q_pest_visit,
            "pest_visit",
            site.id,
            body["answers"],
            completed_at=v.visited_at,
        )
        v.response_id = out.response.id
    if v.proposals:
        b.send(
            db,
            project,
            b.holders(db, project, C.storage_manage, site.id),
            f"pest:{v.id}:trend",
            f"Pest activity trend on {v.visit_no}",
            f"نشاط آفات متكرر في {v.visit_no}",
            path=f"/quality/pest/{v.id}",
            email=False,
        )
    return {**visit_read(db, p, v), "warnings": b.warn_dump(warnings)}


def visit_read(db: Session, p: Principal, v: QPestVisit) -> dict[str, Any]:
    hide = b.hide_names(p, v.project_id)
    codes = {
        str(x.id): x.code
        for x in db.scalars(select(QPestStation).where(QPestStation.site_id == v.site_id))
    }
    return {
        "id": v.id,
        "visit_no": v.visit_no,
        "site_id": v.site_id,
        "provider": b.supplier_ref(db, v.provider_supplier_id),
        "visited_at": v.visited_at,
        "technician_name": None if hide else v.technician_name,
        "chemicals": v.chemicals,
        "station_results": [
            {**r, "code": codes.get(r["station_id"], "")} for r in v.station_results
        ],
        "not_serviced": v.not_serviced,
        "proposals": v.proposals,
        "response_id": v.response_id,
    }


def list_visits(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    return [
        visit_read(db, p, v)
        for v in db.scalars(
            select(QPestVisit)
            .where(QPestVisit.project_id == project.id)
            .order_by(QPestVisit.visited_at.desc())
            .limit(100)
        )
    ]


def get_visit(db: Session, p: Principal, vid: uuid.UUID) -> dict[str, Any]:
    v = db.get(QPestVisit, vid)
    if v is None or not p.can_see_project(v.project_id):
        raise b.not_found(db, p, RT, vid, None)
    project = qc.get_project(db, p, v.project_id)
    b.list_grant(p, project.id)
    return visit_read(db, p, v)


# ---- jobs and the NCR source (list NS `hygiene_pest`) --------------------------------------------


def overdue_alerts(db: Session, at: datetime) -> int:
    """Q-HYG-01: a period that ended yesterday without a check alerts the assignee role and the
    266 holders the next morning (07:12)."""
    n = 0
    for s in db.scalars(select(QCheckSchedule).where(QCheckSchedule.active.is_(True))):
        project = db.get(Project, s.project_id)
        if project is None:
            continue
        today = qc.project_day(project, at)
        yesterday = today - timedelta(days=1)
        for pa, pe in periods(s, yesterday):
            if pe != yesterday or done_dates(db, s, pa, pe):
                continue
            users = b.holders(db, project, C.storage_manage, s.site_id) | {
                a.user_id
                for a in db.scalars(
                    select(RoleAssignment).where(
                        RoleAssignment.project_id == project.id,
                        RoleAssignment.role == s.assignee_role,
                        RoleAssignment.revoked_at.is_(None),
                    )
                )
            }
            zone = db.get(Zone, s.zone_id) if s.zone_id else None
            n += b.send(
                db,
                project,
                users,
                f"hyg:{s.id}:{pa}",
                f"{s.check_type.value} check overdue: {zone.code if zone else ''} ({pa} – {pe})",
                f"فحص متأخر: {zone.code if zone else ''} ({pa} – {pe})",
                path="/quality/hygiene",
                email=False,
            )
    return n


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    v = db.get(QPestVisit, source_id)
    if v is not None and v.project_id == project.id:
        return reg.SourceInfo(
            ref=v.visit_no,
            title=f"Pest activity — {v.visit_no}",
            site_id=v.site_id,
            engagement_id=b.operator_engagement(db, project),
            supplier_id=v.provider_supplier_id,
            item_key=f"PEST:{v.site_id}",
            detection_stage=QDetectionStage.storage,
            requirement_en="No pest activity in the storage areas (pest-control programme).",
            requirement_ar="لا نشاط للآفات في مناطق التخزين.",
            finding_en="; ".join(f"{x['station']}: {', '.join(x['why'])}" for x in v.proposals)
            or "Pest activity recorded.",
            finding_ar="نشاط آفات مسجل.",
            proposed_class=QNcrClass.minor,
        )
    r = db.get(ChecklistResponse, source_id)
    if r is None or r.project_id != project.id or r.owner_type != ResponseOwnerType.q_hygiene:
        raise qc.field_err(
            "source_id",
            "The hygiene check or pest visit is not on this project.",
            "فحص النظافة أو الزيارة ليس في المشروع.",
        )
    return reg.SourceInfo(
        ref=f"{r.template_code} {r.completed_date}",
        title=f"Hygiene check critical failure {r.template_code} {r.completed_date}",
        site_id=r.site_id,
        zone_id=r.zone_id,
        engagement_id=b.operator_engagement(db, project),
        item_key=f"HYG:{r.template_code}",
        detection_stage=QDetectionStage.storage,
        requirement_en="Warehouse hygiene checklist critical items.",
        requirement_ar="البنود الحرجة في قائمة فحص النظافة.",
        finding_en=", ".join(
            a["item_code"] for a in r.answers if a.get("critical") and a.get("compliant") is False
        )
        or "Critical failure.",
        finding_ar="فشل بند حرج.",
        proposed_class=QNcrClass.minor,
    )


_ = QStorageClass
