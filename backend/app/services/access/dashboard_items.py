"""Phase 2 additions to the dashboard expiring-items panel (§8.2) and action panel (§8.3).

Both are scoped by capability 77's grant; names appear only for capability 46 holders, other
callers see "Worker WKR-nnnnnn" (KA-4). Background rechecks show only to capability 56."""

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    CredentialKind,
    CustodyStatus,
    GateReasonCode,
    InductionStatus,
    NotamStatus,
    ObstacleStatus,
    PassApplicationStatus,
    SuspensionState,
    ValidityStatus,
    VehicleStatus,
    WapStatus,
)
from app.core.clock import now
from app.core.config import API_PREFIX
from app.core.enums import Capability, EntityType
from app.core.hse_enums import ActionPanelItem, ExpiringItemKind, Severity
from app.models import (
    Adp,
    AirportPass,
    Avp,
    CredentialSuspension,
    Deployment,
    GateCheck,
    InductionRecord,
    NotamRequest,
    ObstacleClearance,
    OpsEvent,
    PassApplication,
    Project,
    Vehicle,
    Wap,
    Worker,
)
from app.schemas.dashboard import ExpiringItem
from app.services.access import common, lifecycle
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal

K = ExpiringItemKind
LIVE_CRED = (ValidityStatus.active, ValidityStatus.suspended)


class _Ctx:
    def __init__(self, db: Session, p: Principal, project: Project, day: date) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.day = day
        self.grant: Grant | None = p.grant(project.id, Capability.access_kpi_view)
        self.names = common.can_see_names(p, project.id)
        self.refs = Refs(db)
        self._workers: dict[uuid.UUID, Worker] = {}
        self._dep_sites: dict[uuid.UUID, list[uuid.UUID]] = {}

    def ok(self, eng: uuid.UUID | None, sites: list[uuid.UUID] | None = None) -> bool:
        g = self.grant
        if g is None:
            return False
        if g.engagement_ids is not None and (eng is None or eng not in g.engagement_ids):
            return False
        return g.site_ids is None or sites is None or bool(set(sites) & set(g.site_ids))

    def dep_sites(self, dep_id: uuid.UUID) -> list[uuid.UUID]:
        if not self._dep_sites:  # one query for the project instead of one per row
            self._dep_sites = {
                did: list(sites or [])
                for did, sites in self.db.execute(
                    select(Deployment.id, Deployment.site_ids).where(
                        Deployment.project_id == self.project.id
                    )
                )
            }
        if dep_id not in self._dep_sites:
            d = self.db.get(Deployment, dep_id)
            self._dep_sites[dep_id] = list(d.site_ids or []) if d else []
        return self._dep_sites[dep_id]

    def worker(self, wid: uuid.UUID) -> Worker | None:
        if wid not in self._workers:
            w = self.db.get(Worker, wid)
            if w is None:
                return None
            self._workers[wid] = w
        return self._workers[wid]

    def worker_title(self, wid: uuid.UUID) -> tuple[str, str]:
        w = self.worker(wid)
        if w is None:
            return "Worker", "عامل"
        if self.names:
            return f"{w.worker_no} {w.full_name_en}", f"{w.worker_no} {w.full_name_ar}"
        return f"Worker {w.worker_no}", f"العامل {w.worker_no}"


def _item(
    c: _Ctx,
    kind: ExpiringItemKind,
    et: EntityType,
    eid: uuid.UUID | None,
    ref: str | None,
    title: tuple[str, str],
    due: date,
    eng: uuid.UUID | None,
    path: str | None,
    lf: object = None,
) -> ExpiringItem:
    return ExpiringItem(
        kind=kind,
        entity_type=et,
        entity_id=eid,
        ref=ref,
        title_en=title[0],
        title_ar=title[1],
        due_date=due,
        days_left=(due - c.day).days,
        engagement=c.refs.eng(eng) if eng else None,
        detail_path=f"{API_PREFIX}{path}" if path else None,
        limiting_factor=lf,
    )


def expiring(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    horizon: date,
    include_overdue: bool,
) -> list[ExpiringItem]:
    """§8.2 kinds for an airport project (empty without capability 77)."""
    if not project.is_airport:
        return []
    c = _Ctx(db, p, project, day)
    if c.grant is None:
        return []
    pid = project.id
    lo = date.min if include_overdue else day
    out: list[ExpiringItem] = []

    def keep(d: date | None) -> bool:
        return d is not None and lo <= d <= horizon

    # inductions (valid) and re-induction due
    for r in db.scalars(
        select(InductionRecord).where(
            InductionRecord.project_id == pid,
            InductionRecord.status == InductionStatus.valid,
            or_(
                InductionRecord.valid_until.between(lo, horizon),
                InductionRecord.reinduction_due_on.between(lo, horizon),
            ),
        )
    ):
        if not c.ok(r.engagement_id, c.dep_sites(r.deployment_id)):
            continue
        t = c.worker_title(r.worker_id)
        if keep(r.valid_until):
            assert r.valid_until is not None  # noqa: S101
            out.append(_item(c, K.induction_expiry, EntityType.induction_record, r.id,
                             r.induction_no, t, r.valid_until, r.engagement_id,
                             f"/inductions/{r.id}"))  # fmt: skip
        if keep(r.reinduction_due_on):
            assert r.reinduction_due_on is not None  # noqa: S101
            out.append(_item(c, K.reinduction_due, EntityType.induction_record, r.id,
                             r.induction_no, t, r.reinduction_due_on, r.engagement_id,
                             f"/inductions/{r.id}"))  # fmt: skip
    # worker ID expiry (workers currently deployed on the project)
    for dep, w in db.execute(
        select(Deployment, Worker)
        .join(Worker, Worker.id == Deployment.worker_id)
        .where(
            Deployment.project_id == pid,
            Deployment.demobilised_on.is_(None),
            Worker.id_expiry_date.between(lo, horizon),
        )
    ):
        if not c.ok(dep.engagement_id, list(dep.site_ids or [])):
            continue
        c._workers[w.id] = w
        assert w.id_expiry_date is not None  # noqa: S101
        out.append(_item(c, K.worker_id_expiry, EntityType.worker, w.id, w.worker_no,
                         c.worker_title(w.id), w.id_expiry_date, dep.engagement_id,
                         f"/workers/{w.id}"))  # fmt: skip
    # passes, ADPs, AVPs (effective validity) and return due
    cred_models: tuple[tuple[ExpiringItemKind, EntityType, Any, str, str], ...] = (
        (K.airport_pass_expiry, EntityType.airport_pass, AirportPass, "pass_no", "airport-passes"),
        (K.adp_expiry, EntityType.adp, Adp, "adp_no", "adps"),
        (K.avp_expiry, EntityType.avp, Avp, "avp_no", "avps"),
    )
    for kind, et, model, no_attr, path in cred_models:
        for obj in db.scalars(
            select(model).where(
                model.project_id == pid,
                or_(
                    model.validity_status.in_(LIVE_CRED)
                    & model.effective_valid_until.between(lo, horizon),
                    (model.custody_status == CustodyStatus.return_due)
                    & model.return_due_on.between(lo, horizon),
                ),
            )
        ):
            sites = c.dep_sites(obj.deployment_id) if hasattr(obj, "deployment_id") else None
            if not c.ok(obj.engagement_id, sites):
                continue
            if model is Avp:
                v = db.get(Vehicle, obj.vehicle_id)
                title = (
                    (f"{v.vehicle_no} {v.fleet_no}", f"{v.vehicle_no} {v.fleet_no}")
                    if v
                    else ("Vehicle", "مركبة")
                )
            else:
                title = c.worker_title(obj.worker_id)
            ref = getattr(obj, no_attr)
            if obj.validity_status in LIVE_CRED and keep(obj.effective_valid_until):
                out.append(_item(c, kind, et, obj.id, ref, title, obj.effective_valid_until,
                                 obj.engagement_id, f"/{path}/{obj.id}",
                                 obj.limiting_factor))  # fmt: skip
            if obj.custody_status == CustodyStatus.return_due and keep(obj.return_due_on):
                out.append(_item(c, K.pass_return_due, et, obj.id, ref, title,
                                 obj.return_due_on, obj.engagement_id,
                                 f"/{path}/{obj.id}"))  # fmt: skip
    # background recheck due (capability 56 only)
    if p.grant(pid, Capability.background_check_view) is not None:
        apps = {
            a.id: a
            for a in db.scalars(
                select(PassApplication).where(
                    PassApplication.project_id == pid, PassApplication.issued_pass_id.is_not(None)
                )
            )
        }
        for ps in db.scalars(
            select(AirportPass).where(
                AirportPass.project_id == pid,
                AirportPass.validity_status.in_(LIVE_CRED),
                AirportPass.escorted.is_(False),
            )
        ):
            if not c.ok(ps.engagement_id, c.dep_sites(ps.deployment_id)):
                continue
            bg = lifecycle.background(apps.get(ps.application_id))
            due = date.fromisoformat(str(bg["recheck_due"])) if bg.get("recheck_due") else None
            if keep(due):
                assert due is not None  # noqa: S101
                out.append(_item(c, K.bg_recheck_due, EntityType.airport_pass, ps.id,
                                 ps.pass_no, c.worker_title(ps.worker_id), due,
                                 ps.engagement_id, f"/airport-passes/{ps.id}"))  # fmt: skip
    # ADP suspension end
    for s in db.scalars(
        select(CredentialSuspension).where(
            CredentialSuspension.project_id == pid,
            CredentialSuspension.credential_kind == CredentialKind.adp,
            CredentialSuspension.lifted_at.is_(None),
            CredentialSuspension.suspension_end.between(lo, horizon),
        )
    ):
        a = db.get(Adp, s.credential_id)
        if a is None or not c.ok(a.engagement_id, c.dep_sites(a.deployment_id)):
            continue
        assert s.suspension_end is not None  # noqa: S101
        out.append(_item(c, K.adp_suspension_end, EntityType.adp, a.id, a.adp_no,
                         c.worker_title(a.worker_id), s.suspension_end, a.engagement_id,
                         f"/adps/{a.id}"))  # fmt: skip
    # vehicle documents
    for v in db.scalars(
        select(Vehicle).where(Vehicle.project_id == pid, Vehicle.status != VehicleStatus.withdrawn)
    ):
        if not c.ok(v.engagement_id):
            continue
        docs = (
            ("istimara", "Istimara", "الاستمارة", v.istimara_expiry),
            ("insurance", "Insurance", "التأمين", v.insurance_expiry),
            ("mvpi", "MVPI", "الفحص الدوري", v.mvpi_expiry),
        )
        for _key, en, ar, d in docs:
            if keep(d):
                assert d is not None  # noqa: S101
                out.append(_item(c, K.vehicle_document_expiry, EntityType.vehicle, v.id,
                                 v.vehicle_no, (f"{v.vehicle_no} {v.fleet_no} — {en}",
                                                f"{v.vehicle_no} {v.fleet_no} — {ar}"),
                                 d, v.engagement_id, f"/vehicles/{v.id}"))  # fmt: skip
    # WAPs, NOTAMs, obstacle clearances
    for wp in db.scalars(
        select(Wap).where(
            Wap.project_id == pid,
            Wap.revision_of_id.is_(None),
            Wap.status.in_([WapStatus.approved, WapStatus.active, WapStatus.suspended]),
            Wap.valid_to.between(lo, horizon),
        )
    ):
        if c.ok(wp.engagement_id, [wp.site_id]):
            out.append(_item(c, K.wap_expiry, EntityType.wap, wp.id, wp.wap_no,
                             (wp.scope_en, wp.scope_ar), wp.valid_to, wp.engagement_id,
                             f"/waps/{wp.id}"))  # fmt: skip
    for n in db.scalars(
        select(NotamRequest).where(
            NotamRequest.project_id == pid,
            NotamRequest.status == NotamStatus.issued,
            NotamRequest.effective_to_utc.is_not(None),
        )
    ):
        assert n.effective_to_utc is not None  # noqa: S101
        d = common.local_day(n.effective_to_utc)
        if keep(d) and c.ok(n.engagement_id):
            out.append(_item(c, K.notam_expiry, EntityType.notam_request, n.id, n.ntm_no,
                             (f"NOTAM {n.notam_number or n.ntm_no}",
                              f"NOTAM {n.notam_number or n.ntm_no}"),
                             d, n.engagement_id, f"/notam-requests/{n.id}"))  # fmt: skip
    for o in db.scalars(
        select(ObstacleClearance).where(
            ObstacleClearance.project_id == pid,
            ObstacleClearance.status.in_(
                [ObstacleStatus.approved, ObstacleStatus.approved_with_conditions]
            ),
            ObstacleClearance.valid_to.between(lo, horizon),
        )
    ):
        assert o.valid_to is not None  # noqa: S101
        if c.ok(o.engagement_id):
            label = o.equipment_desc or o.equipment_type.value
            out.append(_item(c, K.obstacle_clearance_expiry, EntityType.obstacle_clearance,
                             o.id, o.obs_no, (label, label), o.valid_to, o.engagement_id,
                             f"/obstacle-clearances/{o.id}"))  # fmt: skip
    return out


# ---- action panel ----------------------------------------------------------------------------

LABELS: dict[ActionPanelItem, tuple[str, str]] = {
    ActionPanelItem.pass_applications_stale: ("Pass applications stale", "طلبات تصاريح متأخرة"),
    ActionPanelItem.raised_suspensions_pending: (
        "Raised suspensions awaiting confirmation",
        "إيقافات بانتظار التأكيد",
    ),
    ActionPanelItem.unreturned_overdue: ("Unreturned credentials overdue", "تصاريح غير مُعادة"),
    ActionPanelItem.lost_without_authority_notice: (
        "Lost passes without authority notification",
        "تصاريح مفقودة دون إبلاغ الجهة",
    ),
    ActionPanelItem.waps_approved_blocked: (
        "WAPs approved but blocked today",
        "تصاريح معتمدة ومعطلة اليوم",
    ),
    ActionPanelItem.ops_suspensions_active: ("Active ops suspensions", "إيقافات تشغيلية سارية"),
    ActionPanelItem.notam_not_issued_48h: (
        "NOTAM requests not issued within 48 h of start",
        "طلبات NOTAM غير صادرة قبل 48 ساعة من البدء",
    ),
    ActionPanelItem.revoked_token_scans: (
        "Scans of lost/revoked cards (7 days)",
        "مسح بطاقات مفقودة أو ملغاة (7 أيام)",
    ),
    ActionPanelItem.admitted_despite_denial: (
        "Admitted despite denial (7 days)",
        "دخول رغم الرفض (7 أيام)",
    ),
    ActionPanelItem.induction_language_mismatch: (
        "Inductions with language mismatch (30 days)",
        "تعريفات بلغة غير مطابقة (30 يوماً)",
    ),
}

Adder = Callable[..., None]


def action_items(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    engs: frozenset[uuid.UUID] | None,
    sites: frozenset[uuid.UUID] | None,
    add: Adder,
    link: Callable[[str, str, dict[str, object]], object],
    flt: dict[str, list[str]],
) -> None:
    """Appends the §8.3 entries via the dashboard's ``add(key, count, severity, link, by)``."""
    if not project.is_airport:
        return
    c = _Ctx(db, p, project, day)
    if c.grant is None:
        return
    pid = project.id
    base = f"/projects/{pid}"
    at = now()

    def ok(eng: uuid.UUID | None, s: list[uuid.UUID] | None = None) -> bool:
        if engs is not None and (eng is None or eng not in engs):
            return False
        if sites is not None and s is not None and not set(s) & sites:
            return False
        return c.ok(eng, s)

    s = common.settings(db, pid)
    # stale applications (AP-14)
    stale: Counter[uuid.UUID | None] = Counter()
    for a in db.scalars(
        select(PassApplication).where(
            PassApplication.project_id == pid,
            PassApplication.status == PassApplicationStatus.lodged,
        )
    ):
        if (
            a.lodged_at
            and common.local_day(a.lodged_at) + timedelta(days=s.application_stale_days) < day
            and ok(a.sponsor_engagement_id, c.dep_sites(a.deployment_id))
        ):
            stale[a.sponsor_engagement_id] += 1
    add(ActionPanelItem.pass_applications_stale, sum(stale.values()), Severity.warning,
        link("pass_applications", f"{base}/pass-applications", {"stale": "true", **flt}),
        stale)  # fmt: skip
    # raised suspensions awaiting confirmation
    raised: Counter[uuid.UUID | None] = Counter()
    models: dict[CredentialKind, type] = {
        CredentialKind.induction: InductionRecord,
        CredentialKind.airport_pass: AirportPass,
        CredentialKind.adp: Adp,
        CredentialKind.avp: Avp,
    }
    for susp in db.scalars(
        select(CredentialSuspension).where(
            CredentialSuspension.project_id == pid,
            CredentialSuspension.state == SuspensionState.raised,
            CredentialSuspension.lifted_at.is_(None),
        )
    ):
        model = models.get(susp.credential_kind)
        obj = db.get(model, susp.credential_id) if model else None
        eng = getattr(obj, "engagement_id", None)
        if ok(eng):
            raised[eng] += 1
    add(ActionPanelItem.raised_suspensions_pending, sum(raised.values()), Severity.critical,
        None, raised)  # fmt: skip
    # unreturned overdue (K-55) and lost without authority notice
    overdue: Counter[uuid.UUID | None] = Counter()
    lost: Counter[uuid.UUID | None] = Counter()
    cred_list: tuple[Any, ...] = (AirportPass, Adp, Avp)
    for model in cred_list:
        for obj in db.scalars(
            select(model).where(
                model.project_id == pid,
                model.custody_status.in_([CustodyStatus.return_due, CustodyStatus.lost]),
            )
        ):
            if not ok(obj.engagement_id):
                continue
            if (
                obj.custody_status == CustodyStatus.return_due
                and obj.return_due_on is not None
                and day > obj.return_due_on
            ):
                overdue[obj.engagement_id] += 1
            if (
                model is AirportPass
                and obj.custody_status == CustodyStatus.lost
                and obj.authority_notified_at is None
            ):
                lost[obj.engagement_id] += 1
    add(ActionPanelItem.unreturned_overdue, sum(overdue.values()), Severity.warning,
        link("airport_passes", f"{base}/airport-passes", {"return_overdue": "true", **flt}),
        overdue)  # fmt: skip
    add(ActionPanelItem.lost_without_authority_notice, sum(lost.values()), Severity.critical,
        link("airport_passes", f"{base}/airport-passes",
             {"custody_status": CustodyStatus.lost.value, **flt}), lost)  # fmt: skip
    # WAPs approved-but-blocked today
    blocked: Counter[uuid.UUID | None] = Counter()
    for w in db.scalars(
        select(Wap).where(
            Wap.project_id == pid,
            Wap.status == WapStatus.approved,
            Wap.revision_of_id.is_(None),
            Wap.valid_from <= day,
            Wap.valid_to >= day,
        )
    ):
        if ok(w.engagement_id, [w.site_id]):
            blocked[w.engagement_id] += 1
    add(ActionPanelItem.waps_approved_blocked, sum(blocked.values()), Severity.warning,
        link("waps", f"{base}/waps", {"blocked": "true", **flt}), blocked)  # fmt: skip
    # active ops suspensions
    ops = [
        o for o in db.scalars(
            select(OpsEvent).where(
                OpsEvent.project_id == pid,
                OpsEvent.started_at <= at,
                or_(OpsEvent.ended_at.is_(None), OpsEvent.ended_at > at),
            )
        )
        if sites is None or o.site_id in sites
    ]  # fmt: skip
    add(ActionPanelItem.ops_suspensions_active, len(ops), Severity.critical,
        link("ops_events", f"{base}/ops-events", {"active": "true"}), None)  # fmt: skip
    # NOTAM requests not issued within 48 h of start
    soon = at + timedelta(hours=48)
    ntm: Counter[uuid.UUID | None] = Counter()
    for n in db.scalars(
        select(NotamRequest).where(
            NotamRequest.project_id == pid,
            NotamRequest.status.in_([NotamStatus.submitted_to_ops, NotamStatus.requested_from_ais]),
            NotamRequest.requested_start_utc <= soon,
            NotamRequest.requested_end_utc > at,
        )
    ):
        if ok(n.engagement_id):
            ntm[n.engagement_id] += 1
    add(ActionPanelItem.notam_not_issued_48h, sum(ntm.values()), Severity.critical,
        link("notam_requests", f"{base}/notam-requests",
             {"not_issued_within_hours": "48"}), ntm)  # fmt: skip
    # gate log (last 7 days)
    since = at - timedelta(days=7)
    revoked: Counter[uuid.UUID | None] = Counter()
    admitted: Counter[uuid.UUID | None] = Counter()
    bad = {GateReasonCode.CREDENTIAL_REVOKED.value, GateReasonCode.CREDENTIAL_LOST.value}
    for g in db.scalars(
        select(GateCheck).where(
            GateCheck.project_id == pid,
            GateCheck.occurred_at >= since,
            or_(
                GateCheck.admitted_despite_denial.is_(True),
                GateCheck.reason_codes.overlap(list(bad)),
            ),
        )
    ):
        if not ok(g.engagement_id, [g.site_id] if g.site_id else None):
            continue
        if set(g.reason_codes or []) & bad:
            revoked[g.engagement_id] += 1
        if g.admitted_despite_denial:
            admitted[g.engagement_id] += 1
    since_q = since.isoformat()
    add(ActionPanelItem.revoked_token_scans, sum(revoked.values()), Severity.critical,
        link("gate_log", f"{base}/gate-log",
             {"reason_code": [GateReasonCode.CREDENTIAL_REVOKED.value,
                              GateReasonCode.CREDENTIAL_LOST.value], "since": since_q}),
        revoked)  # fmt: skip
    add(ActionPanelItem.admitted_despite_denial, sum(admitted.values()), Severity.critical,
        link("gate_log", f"{base}/gate-log",
             {"admitted_despite_denial": "true", "since": since_q}), admitted)  # fmt: skip
    # induction records with LANGUAGE_MISMATCH (last 30 days)
    frm = day - timedelta(days=30)
    mism: Counter[uuid.UUID | None] = Counter()
    for r in db.scalars(
        select(InductionRecord).where(
            InductionRecord.project_id == pid,
            InductionRecord.language_mismatch.is_(True),
            InductionRecord.delivered_on > frm,
            InductionRecord.delivered_on <= day,
        )
    ):
        if ok(r.engagement_id, c.dep_sites(r.deployment_id)):
            mism[r.engagement_id] += 1
    add(ActionPanelItem.induction_language_mismatch, sum(mism.values()), Severity.warning,
        link("inductions", f"{base}/inductions",
             {"language_mismatch": "true", "delivered_from": (frm + timedelta(days=1)).isoformat(),
              **flt}), mism)  # fmt: skip
