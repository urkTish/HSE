"""Readiness report per hook code (spec 4-third-party-cert §6.8, HK4-7). Report only: it never
prevents the warn → block switch."""

import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, HookKind, HookProviderStatus, HookSubjectType
from app.core.cert_enums import (
    EquipmentDeploymentStatus,
    HookCodePolicy,
    HookReasonCode,
    HookStage,
    ScaffoldStatus,
)
from app.core.clock import today
from app.core.enums import Capability
from app.core.ptw_enums import PERMIT_TERMINAL
from app.models import (
    Deployment,
    EquipmentDeployment,
    EquipmentItem,
    Permit,
    PermitCrew,
    Scaffold,
    Worker,
)
from app.schemas.cert_config import (
    HookReadinessReport,
    ReadinessAffected,
    ReadinessCode,
    ReadinessSubject,
)
from app.services import projects
from app.services.access import common as acommon
from app.services.access import hooks as ahooks
from app.services.cert import policy, providers
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.permissions import Principal, forbidden_error
from app.services.ptw.common import permit_ref

C = Capability
P = HookProviderStatus
OK = (P.met, P.expiring)


def _at(d: date) -> datetime:
    """Midday local of d (UTC instant) for evaluations on a date."""
    return acommon.local_midnight_utc(d) + timedelta(hours=12)


def pct(n: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(n) * 100 / Decimal(total)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _equipment_subjects(
    db: Session, project_id: uuid.UUID, code: str
) -> list[tuple[str, uuid.UUID, str, str | None]]:
    """On Site items of the code's categories (scaffolds in use for SCAFFOLD-TAG)."""
    if code == "SCAFFOLD-TAG":
        return [
            ("scaffold", sc.id, sc.tag, None)
            for sc in db.scalars(
                select(Scaffold).where(
                    Scaffold.project_id == project_id, Scaffold.status != ScaffoldStatus.dismantled
                )
            )
        ]
    cats = ref.EQUIPMENT_HOOK_CODES.get(code, frozenset())
    rows = db.execute(
        select(EquipmentDeployment, EquipmentItem)
        .join(EquipmentItem, EquipmentItem.id == EquipmentDeployment.equipment_id)
        .where(
            EquipmentDeployment.project_id == project_id,
            EquipmentDeployment.status == EquipmentDeploymentStatus.on_site,
            EquipmentItem.category.in_(list(cats)),
        )
        .order_by(EquipmentDeployment.tag)
    ).all()
    return [
        ("equipment", item.id, dep.tag, f"{item.equipment_no} {item.category.value}")
        for dep, item in rows
    ]


def _personnel_subjects(db: Session, project_id: uuid.UUID, code: str) -> dict[uuid.UUID, Worker]:
    """Mobilised workers whose trade maps to the code plus crew named with that hook on
    non-terminal permits."""
    s = cset.get(db, project_id)
    trades = [t for t, c in (s.trade_cert_requirements or {}).items() if c == code]
    out: dict[uuid.UUID, Worker] = {}
    if trades:
        for dep in db.scalars(
            select(Deployment).where(
                Deployment.project_id == project_id,
                Deployment.status == DeploymentStatus.mobilised,
                Deployment.trade.in_(trades),
            )
        ):
            w = db.get(Worker, dep.worker_id)
            if w is not None:
                out[w.id] = w
    for line in db.scalars(
        select(PermitCrew)
        .join(Permit, Permit.id == PermitCrew.permit_id)
        .where(Permit.project_id == project_id, Permit.status.notin_(list(PERMIT_TERMINAL)))
    ):
        for it in line.eligibility or []:
            if (
                it.get("hook_kind") == HookKind.personnel_certificate.value
                and it.get("code") == code
            ):
                w = db.get(Worker, line.worker_id)
                if w is not None:
                    out[w.id] = w
                break
    return out


def _next_block(st: Any, d: date) -> date:
    """HK4-7: the preview is for the next block date (critical first), else today."""
    if st is None:
        return d
    dates = [
        x
        for x, done in (
            (st.critical_block_from, st.critical_switched_at),
            (st.general_block_from, st.general_switched_at),
        )
        if done is None and x >= d
    ]
    return min(dates) if dates else d


def report(
    db: Session, p: Principal, project_id: uuid.UUID, kind: HookKind, on_date: date | None = None
) -> HookReadinessReport:
    if kind == HookKind.training_course:  # 5-training HK5-9 (capability 143)
        from app.services.train import config as tconfig  # noqa: PLC0415

        return tconfig.readiness(db, p, project_id, on_date)
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, C.cert_kpi_view) is None:
        raise forbidden_error()
    if kind not in (HookKind.personnel_certificate, HookKind.equipment_certificate):
        from app.core.errors import validation_error  # noqa: PLC0415

        raise validation_error("kind", "Readiness is reported for Phase 4 kinds only.")
    d = on_date or today()
    at = _at(d)
    s = cset.get(db, project.id)
    st = policy.state(db, project.id, kind)
    stage = policy.current_stage(st, s, at) if st is not None else HookStage.warn
    crit = cset.critical_codes(s)
    names = acommon.can_see_names(p, project.id)
    codes = []
    failing_workers: set[uuid.UUID] = set()
    failing_tags: set[str] = set()
    for code in policy.codes_of(db, kind):
        not_met: list[ReadinessSubject] = []
        required = 0
        ok = 0
        if kind == HookKind.equipment_certificate:
            for stype, sid, tag, label in _equipment_subjects(db, project.id, code):
                required += 1
                if stype == "scaffold":
                    sc = db.get(Scaffold, sid)
                    assert sc is not None  # noqa: S101
                    r = providers.scaffold_result(sc, at)
                else:
                    ctx = ahooks.HookContext(
                        project_id=project.id, equipment_item_id=sid, equipment_tag=tag
                    )
                    r = providers.check(
                        db, HookSubjectType.equipment_tag, sid, kind, code, at, ctx, project.id
                    )
                if r.status in OK:
                    ok += 1
                else:
                    failing_tags.add(tag.upper())
                    not_met.append(
                        ReadinessSubject(
                            subject_type="scaffold" if stype == "scaffold" else "equipment",
                            subject_id=sid,
                            ref=tag,
                            label=label,
                            reason_code=HookReasonCode(
                                r.reason_code or HookReasonCode.CERT_MISSING.value
                            ),
                            hard_stop=r.hard_stop,
                        )
                    )
        else:
            for w in _personnel_subjects(db, project.id, code).values():
                required += 1
                ctx = ahooks.HookContext(project_id=project.id)
                r = providers.check(
                    db, HookSubjectType.worker, w.id, kind, code, at, ctx, project.id
                )
                if r.status in OK:
                    ok += 1
                else:
                    failing_workers.add(w.id)
                    not_met.append(
                        ReadinessSubject(
                            subject_type="worker",
                            subject_id=w.id,
                            ref=w.worker_no,
                            label=w.full_name_en if names else None,
                            reason_code=HookReasonCode(
                                r.reason_code or HookReasonCode.CERT_MISSING.value
                            ),
                            hard_stop=r.hard_stop,
                        )
                    )
        value = pct(ok, required)
        bf = policy.block_from(st, s, code) if st is not None else None
        codes.append(
            ReadinessCode(
                code=code,
                critical=code in crit,
                policy=policy.code_policy(st, s, code, at)
                if st is not None
                else HookCodePolicy.warn,
                block_from=bf,
                required=required,
                in_force=ok,
                readiness_pct=value,
                readiness_display=f"{value} %" if value is not None else "—",
                not_met=not_met,
            )
        )
    permits = []
    for pm in db.scalars(
        select(Permit).where(
            Permit.project_id == project.id, Permit.status.notin_(list(PERMIT_TERMINAL))
        )
    ):
        crew = {
            c.worker_id for c in db.scalars(select(PermitCrew).where(PermitCrew.permit_id == pm.id))
        }
        from app.models import PermitEquipment  # noqa: PLC0415

        tags = {
            (e.tag or "").upper()
            for e in db.scalars(select(PermitEquipment).where(PermitEquipment.permit_id == pm.id))
        }
        if crew & failing_workers or tags & failing_tags:
            permits.append(permit_ref(pm))
    return HookReadinessReport(
        project_id=project.id,
        kind=kind,
        as_of=d,
        stage=stage,
        codes=codes,
        affected=[
            ReadinessAffected(
                on_date=_next_block(st, d), permits=permits, wap_nos=[], gate_codes=[]
            )
        ],
    )
