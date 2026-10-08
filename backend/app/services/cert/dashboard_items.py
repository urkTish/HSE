# ruff: noqa: E501
"""Phase 4 additions to the dashboard expiring-items panel (4-third-party-cert §8.2) and action
panel (§8.3).

Both need capability 122 and are scoped by its grant (engagement / site scope) and by the
dashboard filters. They appear only on projects where Phase 4 is enabled (a hook policy state
exists), so the Phase 1–3 panels are unchanged elsewhere. Titles carry tags, cert numbers and
worker_no only — never names (P4-4). Viewer/Client sees counts only (KC-5): its expiring items
carry no ref, entity id or detail link.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, HookKind
from app.core.cert_enums import (
    CertificateStatus,
    ClientApprovalStatus,
    DefectCategory,
    DefectStatus,
    EquipmentDeploymentStatus,
    HookStage,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ServiceStatus,
    TpiStatus,
    VerificationStatus,
)
from app.core.clock import now
from app.core.config import API_PREFIX
from app.core.enums import Capability, EntityType
from app.core.hse_enums import ActionPanelItem, ExpiringItemKind, Severity
from app.core.ptw_enums import PERMIT_TERMINAL
from app.models import (
    CertificationBan,
    Deployment,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    HookPolicyState,
    Permit,
    PermitEquipment,
    PersonnelCertificate,
    Project,
    Scaffold,
    Tpi,
    TpiAccreditation,
    TpiClientApproval,
    Worker,
)
from app.schemas.dashboard import ExpiringItem
from app.services.cert import common as cc
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal

K = ExpiringItemKind
A = ActionPanelItem
CS = CertificateStatus
EDS = EquipmentDeploymentStatus
LIVE_CERT = (CS.submitted, CS.accepted)

LABELS: dict[ActionPanelItem, tuple[str, str]] = {
    A.certs_awaiting_review: (
        "Certificates awaiting review > 24 h",
        "شهادات بانتظار المراجعة > 24 ساعة",
    ),
    A.verifications_overdue: ("Certificate verifications overdue", "تحقق الشهادات متأخر"),
    A.verification_failed_undecided: (
        "Verification failed — no decision recorded",
        "فشل التحقق دون قرار مسجل",
    ),
    A.certs_unable_to_verify: ("Certificates unable to verify", "شهادات تعذر التحقق منها"),
    A.a_defects_open: ("Category A defects open", "عيوب الفئة (أ) المفتوحة"),
    A.b_defects_due_3d: ("Category B defects due ≤ 3 days", "عيوب الفئة (ب) المستحقة خلال 3 أيام"),
    A.unusable_equipment_on_permits: (
        "Quarantined / out-of-service equipment named on permits",
        "معدات معزولة أو خارج الخدمة مذكورة في تصاريح",
    ),
    A.arrival_inspections_overdue: ("Arrival inspections overdue", "فحوص الوصول المتأخرة"),
    A.scaffolds_tag_not_valid: (
        "Scaffolds in use with an expired or red tag",
        "سقالات قيد الاستخدام ببطاقة منتهية أو حمراء",
    ),
    A.trade_cert_missing: (
        "Mobilised workers missing their trade certificate",
        "عمال معبؤون دون شهادة مهنتهم",
    ),
    A.hook_block_soon_not_ready: (
        "Hook block date ≤ 7 days with readiness < 100 %",
        "موعد حظر المتطلبات خلال 7 أيام والجاهزية أقل من 100 %",
    ),
    A.ban_reviews_due: ("Certification ban reviews due", "مراجعات حظر الشهادات المستحقة"),
}

_PATHS = {
    EntityType.equipment_certificate: "/equipment-certificates/{}",
    EntityType.personnel_certificate: "/personnel-certificates/{}",
    EntityType.scaffold: "/scaffolds/{}",
    EntityType.equipment_defect: "/defects/{}",
    EntityType.tpi_accreditation: "/tpi-accreditations/{}",
    EntityType.tpi_client_approval: "/tpi-approvals/{}",
    EntityType.hook_policy_state: "/projects/{}/hook-policy",
}

KIND_TITLES: dict[ExpiringItemKind, tuple[str, str]] = {
    K.equipment_cert_expiry: ("Equipment certificate expiry", "انتهاء شهادة معدة"),
    K.personnel_cert_expiry: ("Personnel certificate expiry", "انتهاء شهادة كفاءة"),
    K.scaffold_inspection_due: ("Scaffold inspection due", "موعد فحص السقالة"),
    K.defect_rectification_due: ("Defect rectification due", "موعد إصلاح العيب"),
    K.tpi_accreditation_expiry: ("TPI accreditation expiry", "انتهاء اعتماد جهة الفحص"),
    K.tpi_client_approval_expiry: ("TPI client approval expiry", "انتهاء موافقة العميل على الجهة"),
    K.certificate_verification_due: ("Certificate verification due", "موعد التحقق من الشهادة"),
    K.hook_block_date: ("Hook block date", "موعد حظر المتطلبات"),
}


def enabled(db: Session, project_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(HookPolicyState.id).where(HookPolicyState.project_id == project_id).limit(1)
        )
        is not None
    )


class _Ctx:
    def __init__(self, db: Session, p: Principal, project: Project, day: date) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.day = day
        self.at = now()
        self.grant: Grant | None = p.grant(project.id, Capability.cert_kpi_view)
        scope = p.projects.get(project.id)
        self.counts_only = bool(scope and scope.read_only and not p.is_manager)
        self.refs = Refs(db)
        self._worker_eng: dict[uuid.UUID, uuid.UUID | None] = {}
        self._workers_loaded = False
        self._item_eng: dict[uuid.UUID, tuple[uuid.UUID, bool]] | None = None

    def ok(self, eng: uuid.UUID | None, sites: list[uuid.UUID] | None = None) -> bool:
        g = self.grant
        if g is None:
            return False
        if g.engagement_ids is not None and (eng is None or eng not in g.engagement_ids):
            return False
        return g.site_ids is None or sites is None or bool(set(sites) & set(g.site_ids))

    @property
    def full(self) -> bool:
        g = self.grant
        return g is not None and g.engagement_ids is None and g.site_ids is None

    def worker_eng(self, worker_id: uuid.UUID) -> uuid.UUID | None:
        if not self._workers_loaded:
            self._workers_loaded = True
            # one query: mobilised deployments win over others (as the per-worker lookup did)
            rows = self.db.execute(
                select(Deployment.worker_id, Deployment.engagement_id, Deployment.status).where(
                    Deployment.project_id == self.project.id
                )
            ).all()
            for wid, eng, st in rows:
                if wid not in self._worker_eng or st == DeploymentStatus.mobilised:
                    self._worker_eng[wid] = eng
        return self._worker_eng.get(worker_id)

    def cert_eng(self, cert: Any) -> uuid.UUID | None:
        """Engagement of a certificate: the holder's deployment or the item's deployment."""
        if isinstance(cert, PersonnelCertificate):
            return self.worker_eng(cert.worker_id)
        if self._item_eng is None:
            self._item_eng = {}
            for d in self.db.scalars(
                select(EquipmentDeployment)
                .where(EquipmentDeployment.project_id == self.project.id)
                .order_by(EquipmentDeployment.created_at)
            ):
                live = d.status in cc.LIVE_DEPLOYMENT
                prev = self._item_eng.get(d.equipment_id)
                if prev is None or live or not prev[1]:
                    self._item_eng[d.equipment_id] = (d.engagement_id, live)
        item_id = self.db.scalar(
            select(EquipmentCertLine.equipment_id)
            .where(EquipmentCertLine.certificate_id == cert.id)
            .limit(1)
        )
        hit = self._item_eng.get(item_id) if item_id else None
        return hit[0] if hit else None

    def item(
        self,
        kind: ExpiringItemKind,
        et: EntityType,
        eid: uuid.UUID,
        ref: str | None,
        title: tuple[str, str],
        due: date,
        eng: uuid.UUID | None,
        cert_lf: Any = None,
    ) -> ExpiringItem:
        if self.counts_only:
            en, ar = KIND_TITLES[kind]
            return ExpiringItem(
                kind=kind, entity_type=et, entity_id=None, ref=None, title_en=en, title_ar=ar,
                due_date=due, days_left=(due - self.day).days, engagement=None, detail_path=None,
            )  # fmt: skip
        return ExpiringItem(
            kind=kind,
            entity_type=et,
            entity_id=eid,
            ref=ref,
            title_en=title[0],
            title_ar=title[1],
            due_date=due,
            days_left=(due - self.day).days,
            engagement=self.refs.eng(eng) if eng else None,
            detail_path=f"{API_PREFIX}{_PATHS[et].format(eid)}",
            cert_limiting_factor=cert_lf,
        )


def _deployment(
    db: Session, item_id: uuid.UUID, project_id: uuid.UUID
) -> EquipmentDeployment | None:
    return cc.latest_deployment_on(db, item_id, project_id)


def expiring(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    horizon: date,
    include_overdue: bool,
) -> list[ExpiringItem]:
    """§8.2 kinds (empty without capability 122 or before Phase 4 is enabled)."""
    c = _Ctx(db, p, project, day)
    if c.grant is None or not enabled(db, project.id):
        return []
    pid = project.id
    lo = date.min if include_overdue else day
    out: list[ExpiringItem] = []

    def keep(d: date | None) -> bool:
        return d is not None and lo <= d <= horizon

    # equipment certificate lines of On Site items
    for ln, cert, item in db.execute(
        select(EquipmentCertLine, EquipmentCertificate, EquipmentItem)
        .join(EquipmentCertificate, EquipmentCertificate.id == EquipmentCertLine.certificate_id)
        .join(EquipmentItem, EquipmentItem.id == EquipmentCertLine.equipment_id)
        .where(
            EquipmentCertificate.project_id == pid,
            EquipmentCertificate.status == CS.accepted,
            EquipmentCertLine.superseded_by_line_id.is_(None),
            EquipmentCertLine.valid_until.is_not(None),
            EquipmentCertLine.valid_until <= horizon,
        )
        .order_by(EquipmentCertLine.valid_until)
    ).all():
        if not keep(ln.valid_until):
            continue
        dep = _deployment(db, item.id, pid)
        if (
            dep is None
            or dep.status != EDS.on_site
            or not c.ok(dep.engagement_id, list(dep.site_ids or []))
        ):
            continue
        out.append(
            c.item(
                K.equipment_cert_expiry, EntityType.equipment_certificate, cert.id, dep.tag,
                (f"{dep.tag}: certificate {cert.cert_no} valid until {ln.valid_until}",
                 f"{dep.tag}: الشهادة {cert.cert_no} سارية حتى {ln.valid_until}"),
                ln.valid_until or day, dep.engagement_id, ln.limiting_factor,
            )
        )  # fmt: skip
    # personnel certificates of mobilised holders
    for pc in db.scalars(
        select(PersonnelCertificate).where(
            PersonnelCertificate.project_id == pid,
            PersonnelCertificate.status == CS.accepted,
            PersonnelCertificate.superseded_by_id.is_(None),
            PersonnelCertificate.valid_until.is_not(None),
            PersonnelCertificate.valid_until <= horizon,
        )
    ):
        if not keep(pc.valid_until):
            continue
        mob = db.scalar(
            select(Deployment.engagement_id).where(
                Deployment.worker_id == pc.worker_id,
                Deployment.project_id == pid,
                Deployment.status == DeploymentStatus.mobilised,
            )
        )
        if mob is None or not c.ok(mob):
            continue
        w = db.get(Worker, pc.worker_id)
        wno = w.worker_no if w else ""
        assert pc.valid_until is not None  # noqa: S101
        out.append(
            c.item(
                K.personnel_cert_expiry, EntityType.personnel_certificate, pc.id, pc.cert_no,
                (f"{wno}: {pc.cert_type} {pc.cert_no or ''} valid until {pc.valid_until}",
                 f"{wno}: {pc.cert_type} {pc.cert_no or ''} سارية حتى {pc.valid_until}"),
                pc.valid_until, mob, pc.limiting_factor,
            )
        )  # fmt: skip
    # scaffold tags (In Use)
    for sc in db.scalars(
        select(Scaffold).where(
            Scaffold.project_id == pid,
            Scaffold.status == ScaffoldStatus.in_use,
            Scaffold.tag_valid_until.is_not(None),
        )
    ):
        if not keep(sc.tag_valid_until) or not c.ok(sc.engagement_id):
            continue
        assert sc.tag_valid_until is not None  # noqa: S101
        out.append(
            c.item(
                K.scaffold_inspection_due, EntityType.scaffold, sc.id, sc.tag,
                (f"{sc.tag}: tag valid until {sc.tag_valid_until}",
                 f"{sc.tag}: البطاقة سارية حتى {sc.tag_valid_until}"),
                sc.tag_valid_until, sc.engagement_id,
            )
        )  # fmt: skip
    # defects (open / rectified with a due date)
    for x in db.scalars(
        select(EquipmentDefect).where(
            EquipmentDefect.project_id == pid,
            EquipmentDefect.status.in_([DefectStatus.open, DefectStatus.rectified]),
            EquipmentDefect.due_date.is_not(None),
        )
    ):
        if not keep(x.due_date) or not c.ok(x.engagement_id):
            continue
        assert x.due_date is not None  # noqa: S101
        out.append(
            c.item(
                K.defect_rectification_due, EntityType.equipment_defect, x.id, x.defect_no,
                (f"Defect {x.defect_no} ({x.category.value}): rectification due",
                 f"العيب {x.defect_no} ({x.category.value}): موعد الإصلاح"),
                x.due_date, x.engagement_id,
            )
        )  # fmt: skip
    # certificate verification due
    for model, et in (
        (EquipmentCertificate, EntityType.equipment_certificate),
        (PersonnelCertificate, EntityType.personnel_certificate),
    ):
        rows: list[Any] = list(db.scalars(
            select(model).where(
                model.project_id == pid,
                model.status.in_(LIVE_CERT),
                model.verification_status == VerificationStatus.not_verified,
                model.verification_due_on.is_not(None),
            )
        ))  # fmt: skip
        for cert in rows:
            if not keep(cert.verification_due_on):
                continue
            eng = c.cert_eng(cert)
            if c.grant is not None and c.grant.engagement_ids is not None and not c.ok(eng):
                continue
            out.append(
                c.item(
                    K.certificate_verification_due, et, cert.id, cert.cert_no,
                    (f"Verify {cert.cert_no} with the TPI", f"التحقق من {cert.cert_no} لدى الجهة"),
                    cert.verification_due_on, eng,
                )
            )  # fmt: skip
    # TPI accreditations / client approvals (project-wide grants only)
    if c.full:
        for a, t in db.execute(
            select(TpiAccreditation, Tpi)
            .join(Tpi, Tpi.id == TpiAccreditation.tpi_id)
            .where(Tpi.status.in_([TpiStatus.approved, TpiStatus.suspended]))
        ).all():
            if keep(a.valid_until):
                out.append(
                    c.item(
                        K.tpi_accreditation_expiry, EntityType.tpi_accreditation, a.id, t.tpi_code,
                        (f"{t.tpi_code}: accreditation {a.accreditation_no} valid until {a.valid_until}",
                         f"{t.tpi_code}: الاعتماد {a.accreditation_no} ساري حتى {a.valid_until}"),
                        a.valid_until, None,
                    )
                )  # fmt: skip
        for ap, t in db.execute(
            select(TpiClientApproval, Tpi)
            .join(Tpi, Tpi.id == TpiClientApproval.tpi_id)
            .where(
                TpiClientApproval.project_id == pid,
                TpiClientApproval.status == ClientApprovalStatus.active,
            )
        ).all():
            if keep(ap.valid_until):
                out.append(
                    c.item(
                        K.tpi_client_approval_expiry, EntityType.tpi_client_approval, ap.id, t.tpi_code,
                        (f"{t.tpi_code}: client approval {ap.approval_ref} valid until {ap.valid_until}",
                         f"{t.tpi_code}: موافقة العميل {ap.approval_ref} سارية حتى {ap.valid_until}"),
                        ap.valid_until, None,
                    )
                )  # fmt: skip
    # hook block dates (not yet switched)
    for st in db.scalars(
        select(HookPolicyState).where(
            HookPolicyState.project_id == pid, HookPolicyState.stage != HookStage.block
        )
    ):
        for scope_, when, done in (
            ("Critical codes", st.critical_block_from, st.critical_switched_at),
            ("Other codes", st.general_block_from, st.general_switched_at),
        ):
            if done is not None or not keep(when) or when < day:
                continue
            ar_scope = "الرموز الحرجة" if scope_ == "Critical codes" else "الرموز الأخرى"
            out.append(
                ExpiringItem(
                    kind=K.hook_block_date, entity_type=EntityType.hook_policy_state, entity_id=None if c.counts_only else st.id,
                    ref=None if c.counts_only else "hook policy",
                    title_en=f"{st.kind.value}: {scope_} block from {when}",
                    title_ar=f"{st.kind.value}: {ar_scope} تُحظر اعتباراً من {when}",
                    due_date=when, days_left=(when - day).days, engagement=None,
                    detail_path=None if c.counts_only else f"{API_PREFIX}{_PATHS[EntityType.hook_policy_state].format(pid)}",
                )
            )  # fmt: skip
    return out


Adder = Callable[..., None]


_READY: dict[tuple[Any, ...], tuple[float, int]] = {}
READY_TTL_S = 300.0


def _not_ready(
    db: Session,
    p: Principal,
    pid: uuid.UUID,
    kind: HookKind,
    day: date,
    soon: tuple[date, ...],
    readiness: Any,
) -> int:
    """Codes blocking within 7 days whose readiness is < 100 %. The readiness report evaluates
    every subject (seconds on a large project), so this planning count is cached per (project,
    kind, day) for 5 minutes; the readiness report itself is always live."""
    import time  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415

    key = (pid, kind, day, soon)
    hit = _READY.get(key)
    t = time.monotonic()
    caching = get_settings().kpi_cache_seconds > 0  # the same switch as the KPI cache
    if caching and hit is not None and t - hit[0] < READY_TTL_S:
        return hit[1]
    rep = readiness.report(db, p, pid, kind, day)
    n = sum(1 for x in rep.codes if x.block_from in soon and x.required and x.in_force < x.required)
    if len(_READY) > 256:
        _READY.clear()
    _READY[key] = (t, n)
    return n


def action_items(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    engs: frozenset[uuid.UUID] | None,
    sites: frozenset[uuid.UUID] | None,
    add: Adder,
    link: Callable[[str, str, dict[str, Any]], object],
    flt: dict[str, list[str]],
) -> None:
    """Appends the §8.3 entries via the dashboard's ``add(key, count, severity, link, by)``."""
    c = _Ctx(db, p, project, day)
    if c.grant is None or not enabled(db, project.id):
        return
    pid = project.id
    base = f"/projects/{pid}"
    at = c.at
    eflt = {k: v for k, v in flt.items() if k == "engagement_id"}

    def ok(eng: uuid.UUID | None, s: list[uuid.UUID] | None = None) -> bool:
        if engs is not None and (eng is None or eng not in engs):
            return False
        if sites is not None and s is not None and s and not set(s) & sites:
            return False
        return c.ok(eng, s or None)

    def dep_of(item_id: uuid.UUID) -> EquipmentDeployment | None:
        return _deployment(db, item_id, pid)

    eng_of = c.cert_eng

    certs: list[Any] = [
        *db.scalars(select(EquipmentCertificate).where(EquipmentCertificate.project_id == pid, EquipmentCertificate.status.in_(LIVE_CERT))),
        *db.scalars(select(PersonnelCertificate).where(PersonnelCertificate.project_id == pid, PersonnelCertificate.status.in_(LIVE_CERT))),
    ]  # fmt: skip
    eq_link = f"{base}/equipment-certificates"
    pc_link = f"{base}/personnel-certificates"
    review: Counter[uuid.UUID | None] = Counter()
    overdue: Counter[uuid.UUID | None] = Counter()
    failed: Counter[uuid.UUID | None] = Counter()
    unable: Counter[uuid.UUID | None] = Counter()
    for x in certs:
        eng = eng_of(x)
        if not ok(eng):
            continue
        if (
            x.status == CS.submitted
            and x.submitted_at
            and at - x.submitted_at > timedelta(hours=24)
        ):
            review[eng] += 1
        vs = x.verification_status
        if (
            vs == VerificationStatus.not_verified
            and x.verification_due_on
            and x.verification_due_on < day
        ):
            overdue[eng] += 1
        elif vs == VerificationStatus.failed:
            failed[eng] += 1
        elif vs == VerificationStatus.unable_to_verify:
            unable[eng] += 1
    add(A.certs_awaiting_review, sum(review.values()), Severity.warning,
        link("equipment_certificates", eq_link, {"status": [CS.submitted.value], **eflt}), review)  # fmt: skip
    add(A.verifications_overdue, sum(overdue.values()), Severity.warning,
        link("verification_log", f"{base}/verification-log", eflt), overdue)  # fmt: skip
    add(A.verification_failed_undecided, sum(failed.values()), Severity.critical,
        link("equipment_certificates", eq_link, {"verification_status": [VerificationStatus.failed.value], **eflt}), failed)  # fmt: skip
    add(A.certs_unable_to_verify, sum(unable.values()), Severity.warning,
        link("personnel_certificates", pc_link, {"verification_status": [VerificationStatus.unable_to_verify.value], **eflt}), unable)  # fmt: skip
    # defects
    defects_link = f"{base}/defects"
    a_open: Counter[uuid.UUID | None] = Counter()
    b_due: Counter[uuid.UUID | None] = Counter()
    for d in db.scalars(
        select(EquipmentDefect).where(
            EquipmentDefect.project_id == pid,
            EquipmentDefect.status.in_([DefectStatus.open, DefectStatus.rectified]),
        )
    ):
        if not ok(d.engagement_id):
            continue
        if d.category == DefectCategory.A:
            a_open[d.engagement_id] += 1
        elif (
            d.category == DefectCategory.B and d.due_date and d.due_date <= day + timedelta(days=3)
        ):
            b_due[d.engagement_id] += 1
    add(A.a_defects_open, sum(a_open.values()), Severity.critical,
        link("defects", defects_link, {"category": ["A"], "status": [DefectStatus.open.value, DefectStatus.rectified.value], **eflt}), a_open)  # fmt: skip
    add(A.b_defects_due_3d, sum(b_due.values()), Severity.warning,
        link("defects", defects_link, {"category": ["B"], **eflt}), b_due)  # fmt: skip
    # unusable items named on non-terminal permits
    unusable: Counter[uuid.UUID | None] = Counter()
    seen: set[uuid.UUID] = set()
    for line, _permit in db.execute(
        select(PermitEquipment, Permit)
        .join(Permit, Permit.id == PermitEquipment.permit_id)
        .where(Permit.project_id == pid, Permit.status.notin_(list(PERMIT_TERMINAL)), PermitEquipment.equipment_item_id.is_not(None))
    ).all():  # fmt: skip
        if line.equipment_item_id in seen:
            continue
        item = db.get(EquipmentItem, line.equipment_item_id)
        if item is None or item.service_status not in (
            ServiceStatus.quarantined,
            ServiceStatus.out_of_service,
        ):
            continue
        dep = dep_of(item.id)
        if (
            dep is None
            or dep.status != EDS.on_site
            or not ok(dep.engagement_id, list(dep.site_ids or []))
        ):
            continue
        seen.add(item.id)
        unusable[dep.engagement_id] += 1
    add(A.unusable_equipment_on_permits, sum(unusable.values()), Severity.critical,
        link("equipment_deployments", f"{base}/equipment-deployments", {"status": [EDS.on_site.value], **eflt}), unusable)  # fmt: skip
    # arrival inspections overdue (EM-3)
    from app.services.cert import settings as cset  # noqa: PLC0415

    hours = cset.get(db, pid).arrival_inspection_hours
    arrival: Counter[uuid.UUID | None] = Counter()
    for dep in db.scalars(
        select(EquipmentDeployment).where(
            EquipmentDeployment.project_id == pid,
            EquipmentDeployment.status == EDS.on_site,
            EquipmentDeployment.arrival_inspection_passed.is_(False),
        )
    ):
        if (
            dep.arrived_at
            and at - dep.arrived_at > timedelta(hours=hours)
            and ok(dep.engagement_id, list(dep.site_ids or []))
        ):
            arrival[dep.engagement_id] += 1
    add(A.arrival_inspections_overdue, sum(arrival.values()), Severity.warning,
        link("equipment_deployments", f"{base}/equipment-deployments", {"status": [EDS.on_site.value], **eflt}), arrival)  # fmt: skip
    # scaffolds In Use with an expired or red tag
    scf: Counter[uuid.UUID | None] = Counter()
    for sc in db.scalars(
        select(Scaffold).where(Scaffold.project_id == pid, Scaffold.status == ScaffoldStatus.in_use)
    ):
        bad = sc.tag_status in (
            ScaffoldTagStatus.red,
            ScaffoldTagStatus.expired,
            ScaffoldTagStatus.inspection_required,
        ) or (sc.tag_valid_until is not None and sc.tag_valid_until < day)
        if bad and ok(sc.engagement_id):
            scf[sc.engagement_id] += 1
    add(A.scaffolds_tag_not_valid, sum(scf.values()), Severity.critical,
        link("scaffolds", f"{base}/scaffolds", {"status": [ScaffoldStatus.in_use.value], **eflt}), scf)  # fmt: skip
    # PC-12 trade certificate missing (set-based: one query per table)
    from app.services.cert import settings as cset  # noqa: PLC0415

    trade: Counter[uuid.UUID | None] = Counter()
    reqs = dict(cset.get(db, pid).trade_cert_requirements or {})
    if reqs:
        held = set(
            db.execute(
                select(PersonnelCertificate.worker_id, PersonnelCertificate.cert_type).where(
                    PersonnelCertificate.project_id == pid,
                    PersonnelCertificate.cert_type.in_(set(reqs.values())),
                    PersonnelCertificate.status == CS.accepted,
                    PersonnelCertificate.valid_until >= day,
                )
            ).all()
        )
        # Certificates are personal: a card held on another project counts too.
        held |= set(
            db.execute(
                select(PersonnelCertificate.worker_id, PersonnelCertificate.cert_type).where(
                    PersonnelCertificate.project_id != pid,
                    PersonnelCertificate.cert_type.in_(set(reqs.values())),
                    PersonnelCertificate.status == CS.accepted,
                    PersonnelCertificate.valid_until >= day,
                )
            ).all()
        )
        for wid, eng_id, tr in db.execute(
            select(Deployment.worker_id, Deployment.engagement_id, Deployment.trade).where(
                Deployment.project_id == pid, Deployment.status == DeploymentStatus.mobilised
            )
        ).all():
            code = reqs.get(tr.value) if tr is not None else None
            if code and ok(eng_id) and (wid, code) not in held:
                trade[eng_id] += 1
    add(A.trade_cert_missing, sum(trade.values()), Severity.warning,
        link("personnel_certificates", pc_link, eflt), trade)  # fmt: skip
    # hook block ≤ 7 days with readiness < 100 %
    not_ready = 0
    if c.full:
        from app.services.cert import readiness  # noqa: PLC0415

        for st in db.scalars(
            select(HookPolicyState).where(
                HookPolicyState.project_id == pid,
                HookPolicyState.stage != HookStage.block,
                # training codes have their own item (5-training §8.3)
                HookPolicyState.kind != HookKind.training_course,
            )
        ):
            soon = [
                w for w, done in ((st.critical_block_from, st.critical_switched_at), (st.general_block_from, st.general_switched_at))
                if done is None and day <= w <= day + timedelta(days=7)
            ]  # fmt: skip
            if not soon:
                continue
            not_ready += _not_ready(db, p, pid, HookKind(st.kind), day, tuple(soon), readiness)
    add(A.hook_block_soon_not_ready, not_ready, Severity.warning,
        link("hook_readiness", f"{base}/hook-readiness", {}), None)  # fmt: skip
    # ban reviews due (HSE Manager / Officer: decision 8)
    bans = 0
    if c.full and not c.counts_only:
        from app.core.cert_enums import BanStatus  # noqa: PLC0415

        bans = len(
            list(
                db.scalars(
                    select(CertificationBan.id).where(
                        CertificationBan.status == BanStatus.active,
                        CertificationBan.review_due_on <= day,
                    )
                )
            )
        )
    add(A.ban_reviews_due, bans, Severity.warning,
        link("certification_bans", "/certification-bans", {"status": ["active"]}), None)  # fmt: skip
