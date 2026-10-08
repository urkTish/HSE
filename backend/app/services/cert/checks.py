"""Sticker and certification checks (spec 4-third-party-cert VF-8, VF-9) and the gate equipment
check for QR kind EQ (GE-1…GE-7). No personal data on equipment / scaffold cards."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    GateDirection,
    GateReasonCode,
    GateResult,
    GateSubjectKind,
    GateType,
    QrKind,
    QrTokenStatus,
    SuspendedContractorGateMode,
)
from app.core.cert_enums import (
    CertCheckResult,
    CertCheckSubject,
    CertificateStatus,
    EquipmentDeploymentStatus,
    LineResult,
    ServiceStatus,
)
from app.core.clock import now
from app.core.enums import AuditAction, Capability, ContractorStatus, EntityType
from app.core.errors import ErrorCode, validation_error
from app.models import (
    Contractor,
    Deployment,
    EquipmentDeployment,
    EquipmentItem,
    PersonnelCertificate,
    ProjectEngagement,
    QrToken,
    Scaffold,
    Tpi,
    Worker,
    Zone,
)
from app.schemas.cert_check import (
    CertCheckRequest,
    CertCheckResponse,
    EquipmentCheckCard,
    PersonCheckCard,
    PersonCheckCertificate,
    ScaffoldCheckCard,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.cert import common as cc
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.cert import validity
from app.services.permissions import Principal

C = Capability
G = GateReasonCode
DS = EquipmentDeploymentStatus
SS = ServiceStatus
R = ref.R

_REASON_MAP: dict[Any, ErrorCode] = {
    R.CERT_EXPIRED: ErrorCode.CERT_EXPIRED,
    R.CERT_MISSING: ErrorCode.CERT_MISSING,
    R.CERT_UNVERIFIED: ErrorCode.CERT_UNVERIFIED,
    R.CERT_SUSPENDED: ErrorCode.CERT_SUSPENDED,
    R.CERT_REVOKED: ErrorCode.CERT_REVOKED,
    R.CERT_HOLDER_BANNED: ErrorCode.CERT_HOLDER_BANNED,
    R.TPI_BLACKLISTED: ErrorCode.CERT_REVOKED,
}


# ---- cards ---------------------------------------------------------------------------------------


def equipment_card(
    db: Session, d: EquipmentDeployment, item: EquipmentItem, at: datetime
) -> EquipmentCheckCard:
    ic = validity.current_line(db, item.id, at, d.project_id)
    line, cert = ic.line, ic.cert
    t = db.get(Tpi, cert.tpi_id) if cert else None
    usable = item.service_status == SS.in_service and ic.ev.in_force
    restricted = (
        usable
        and line is not None
        and (
            line.result == LineResult.pass_with_conditions
            or bool(line.limitations)
            or ic.ev.expiring
        )
    )
    colour = "green" if usable and not restricted else ("amber" if usable else "red")
    due = d.status == DS.on_site and not d.arrival_inspection_passed
    return EquipmentCheckCard(
        deployment_id=d.id,
        project_code=cc.project_code(db, d.project_id),
        tag=d.tag,
        equipment_no=item.equipment_no,
        category=item.category,
        owner_short_code=cc.owner_code(db, item.owner_contractor_id),
        service_status=item.service_status,
        service_status_reason=item.service_status_reason,
        colour=colour,
        cert_no=cert.cert_no if cert else None,
        tpi_code=t.tpi_code if t else None,
        valid_until=line.valid_until if line else None,
        swl_t=line.swl_t if line else None,
        limitations=cc.limitation_reads(line.limitations if line else []),
        arrival_inspection_due=due,
    )


def scaffold_card(db: Session, sc: Scaffold, at: datetime) -> ScaffoldCheckCard:
    from app.services.cert import scaffolds  # noqa: PLC0415

    d = acommon.local_day(at)
    z = db.get(Zone, sc.zone_id)
    yellow = scaffolds.tag_state(sc, d).value == "yellow"
    return ScaffoldCheckCard(
        scaffold_id=sc.id,
        project_code=cc.project_code(db, sc.project_id),
        tag=sc.tag,
        scaffold_no=sc.scaffold_no,
        zone_code=z.code if z else "",
        status=sc.status,
        tag_status=scaffolds.tag_state(sc, d),
        tag_valid_until=sc.tag_valid_until,
        usable_today=scaffolds.usable(sc, d),
        load_class=sc.load_class,
        restrictions_en=sc.restrictions_en if yellow else None,
        restrictions_ar=sc.restrictions_ar if yellow else None,
    )


def person_card(db: Session, w: Worker, project_id: uuid.UUID, at: datetime) -> PersonCheckCard:
    """VF-9: name, worker_no, photo, and per type the latest relevant certificate; never ID
    numbers, scans, the medical flag or verification-failure details."""
    from app.services.access import gates  # noqa: PLC0415

    dep = db.scalar(
        select(Deployment)
        .where(Deployment.worker_id == w.id, Deployment.project_id == project_id)
        .order_by(Deployment.mobilised_on.desc())
        .limit(1)
    )
    con = None
    if dep is not None and dep.engagement_id is not None:
        eng = db.get(ProjectEngagement, dep.engagement_id)
        con = db.get(Contractor, eng.contractor_id) if eng else None
    seen: set[str] = set()
    certs = []
    for pc in validity.worker_certs(db, w.id):
        if (
            pc.status in (CertificateStatus.superseded, CertificateStatus.rejected)
            or pc.cert_type in seen
        ):
            continue
        seen.add(pc.cert_type)
        ev = validity.eval_personnel(db, pc, at, None, None, project_id)
        t = db.get(Tpi, pc.tpi_id)
        en, ar = cset.type_label(db, pc.cert_type)
        certs.append(
            PersonCheckCertificate(
                cert_type=pc.cert_type,
                cert_type_label_en=en,
                cert_type_label_ar=ar,
                cert_no=pc.cert_no or "",
                tpi_code=t.tpi_code if t else "",
                level=pc.level.value if pc.level else None,
                valid_until=pc.valid_until,
                in_force=ev.in_force,
                not_in_force_reason=None
                if ev.in_force
                else _REASON_MAP.get(ev.reason, ErrorCode.CERT_MISSING),
                scope_categories=list(pc.scope_categories or []),
                max_capacity_t=pc.max_capacity_t,
                limitations=cc.plimitation_reads(pc.limitations),
            )
        )
    return PersonCheckCard(
        worker_id=w.id,
        worker_no=w.worker_no,
        full_name_en=w.full_name_en,
        full_name_ar=w.full_name_ar,
        photo_url=gates._photo_url(db, w.id),
        employer_short_code=con.short_code if con else None,
        trade=dep.trade if dep else None,
        certificates=certs,
    )


# ---- VF-8 / VF-9 ---------------------------------------------------------------------------------


def _resp(result: CertCheckResult, en: str, ar: str, **kw: Any) -> CertCheckResponse:
    return CertCheckResponse(checked_at=now(), result=result, message_en=en, message_ar=ar, **kw)


def _unknown(
    code: ErrorCode = ErrorCode.TOKEN_UNKNOWN, qr_kind: QrKind | None = None
) -> CertCheckResponse:
    if code == ErrorCode.OUT_OF_SCOPE:
        return _resp(
            CertCheckResult.unknown,
            "Outside your scope.",
            "خارج نطاق صلاحيتك.",
            qr_kind=qr_kind,
            subject=None,
            reason_code=code,
        )
    return _resp(
        CertCheckResult.unknown,
        "Not recognised.",
        "غير معروف.",
        qr_kind=qr_kind,
        subject=None,
        reason_code=code,
    )


def _log_view(
    db: Session, p: Principal, project_id: uuid.UUID, entity: EntityType, eid: uuid.UUID
) -> None:
    audit.record(
        db,
        AuditAction.cert_check_view,
        p.actor(project_id),
        entity_type=entity,
        entity_id=eid,
        project_id=project_id,
    )


def _eq_subject(db: Session, t: QrToken) -> tuple[EquipmentDeployment | None, Scaffold | None]:
    d = db.get(EquipmentDeployment, t.subject_id)
    if d is not None:
        return d, None
    return None, db.get(Scaffold, t.subject_id)


def _scope(
    db: Session, p: Principal, project_id: uuid.UUID, eng: uuid.UUID | None, sites: list[uuid.UUID]
) -> bool:
    return acommon.grant_covers(p.grant(project_id, C.cert_check), sites, eng)


def check(db: Session, p: Principal, body: CertCheckRequest) -> CertCheckResponse:
    given = [x for x in (body.payload, body.printed_ref, body.cert_no) if x]
    if len(given) != 1:
        raise validation_error("payload", "Send exactly one of payload, printed_ref or cert_no.")
    if not p.has_any(C.cert_check):
        from app.services.permissions import forbidden_error  # noqa: PLC0415

        raise forbidden_error()
    at = now()
    if body.cert_no:
        if body.project_id is None:
            raise validation_error("project_id", "Choose the project.")
        stmt = select(PersonnelCertificate).where(
            PersonnelCertificate.project_id == body.project_id,
            func.upper(PersonnelCertificate.cert_no) == body.cert_no.strip().upper(),
            PersonnelCertificate.status.notin_([CertificateStatus.draft]),
        )
        if body.tpi_code:
            stmt = stmt.join(Tpi, Tpi.id == PersonnelCertificate.tpi_id).where(
                func.upper(Tpi.tpi_code) == body.tpi_code.strip().upper()
            )
        rows = list(db.scalars(stmt))
        if not rows or len({r.worker_id for r in rows}) > 1:
            return _unknown()
        return _person(db, p, rows[0].worker_id, body.project_id, at, None)
    t: QrToken | None = None
    if body.payload:
        m = acommon.QR_RE.match(body.payload.strip())
        if m:
            t = db.scalar(select(QrToken).where(QrToken.token == m.group(2)))
            if t is not None and t.kind.value != m.group(1):
                t = None
    else:
        if body.project_id is None:
            raise validation_error("project_id", "Choose the project.")
        r = " ".join((body.printed_ref or "").split()).upper()
        cands = list(
            db.scalars(
                select(QrToken)
                .where(
                    QrToken.project_id == body.project_id,
                    QrToken.kind == QrKind.EQ,
                    func.upper(QrToken.printed_ref) == r,
                )
                .order_by(QrToken.created_at.desc())
            )
        )
        active = [c for c in cands if c.status == QrTokenStatus.active]
        t = (active or cands)[0] if (active or cands) else None
    if t is None or t.kind not in (QrKind.EQ, QrKind.AC):
        return _unknown(qr_kind=t.kind if t else None)
    if t.kind == QrKind.AC:
        dep = db.get(Deployment, t.subject_id)
        if dep is None:
            return _unknown(qr_kind=t.kind)
        if not _scope(db, p, dep.project_id, dep.engagement_id, list(dep.site_ids or [])):
            return _unknown(ErrorCode.OUT_OF_SCOPE, QrKind.AC)
        if t.status != QrTokenStatus.active:
            return _resp(
                CertCheckResult.revoked_token,
                "Card revoked.",
                "البطاقة ملغاة.",
                qr_kind=QrKind.AC,
                subject=CertCheckSubject.person,
                reason_code=ErrorCode.CREDENTIAL_REVOKED,
            )
        return _person(db, p, dep.worker_id, dep.project_id, at, QrKind.AC)
    d, sc = _eq_subject(db, t)
    if d is not None:
        if not _scope(db, p, d.project_id, d.engagement_id, list(d.site_ids or [])):
            return _unknown(ErrorCode.OUT_OF_SCOPE, QrKind.EQ)
        _log_view(db, p, d.project_id, EntityType.equipment_deployment, d.id)
        if t.status != QrTokenStatus.active:
            return _resp(
                CertCheckResult.revoked_token,
                "Sticker revoked — do not use.",
                "الملصق ملغى — لا تستخدم.",
                qr_kind=QrKind.EQ,
                subject=CertCheckSubject.equipment,
                reason_code=ErrorCode.CREDENTIAL_REVOKED,
            )
        item = db.get(EquipmentItem, d.equipment_id)
        assert item is not None  # noqa: S101
        card = equipment_card(db, d, item, at)
        res, code = _equipment_result(card)
        en, ar = _texts(res)
        return _resp(
            res,
            en,
            ar,
            qr_kind=QrKind.EQ,
            subject=CertCheckSubject.equipment,
            reason_code=code,
            equipment=card,
        )
    if sc is not None:
        z = db.get(Zone, sc.zone_id)
        if not _scope(db, p, sc.project_id, sc.engagement_id, [z.site_id] if z else []):
            return _unknown(ErrorCode.OUT_OF_SCOPE, QrKind.EQ)
        _log_view(db, p, sc.project_id, EntityType.scaffold, sc.id)
        if t.status != QrTokenStatus.active:
            return _resp(
                CertCheckResult.revoked_token,
                "Sticker revoked — do not use.",
                "الملصق ملغى — لا تستخدم.",
                qr_kind=QrKind.EQ,
                subject=CertCheckSubject.scaffold,
                reason_code=ErrorCode.CREDENTIAL_REVOKED,
            )
        scard = scaffold_card(db, sc, at)
        if not scard.usable_today:
            res, code = CertCheckResult.not_usable, ErrorCode.SCAFFOLD_TAG_RED
            if scard.tag_status.value == "expired":
                code = ErrorCode.SCAFFOLD_INSPECTION_OVERDUE
            elif scard.tag_status.value == "inspection_required":
                code = ErrorCode.SCAFFOLD_INSPECTION_REQUIRED
        elif scard.tag_status.value == "yellow":
            res, code = CertCheckResult.restricted, ErrorCode.SCAFFOLD_YELLOW_TAG
        else:
            res, code = CertCheckResult.in_service, None
        en, ar = _texts(res)
        return _resp(
            res,
            en,
            ar,
            qr_kind=QrKind.EQ,
            subject=CertCheckSubject.scaffold,
            reason_code=code,
            scaffold=scard,
        )
    return _unknown(qr_kind=QrKind.EQ)


def _texts(res: CertCheckResult) -> tuple[str, str]:
    return {
        CertCheckResult.in_service: ("In service — OK to use.", "في الخدمة — يسمح بالاستخدام."),
        CertCheckResult.restricted: ("Use with restrictions.", "استخدام بقيود."),
        CertCheckResult.not_usable: ("DO NOT USE.", "ممنوع الاستخدام."),
    }.get(res, ("", ""))


def _equipment_result(card: EquipmentCheckCard) -> tuple[CertCheckResult, ErrorCode | None]:
    if card.colour == "green":
        return CertCheckResult.in_service, None
    if card.colour == "amber":
        return CertCheckResult.restricted, None
    code = {
        SS.out_of_service: ErrorCode.EQUIPMENT_OUT_OF_SERVICE,
        SS.blacklisted: ErrorCode.EQUIPMENT_BLACKLISTED,
        SS.retired: ErrorCode.EQUIPMENT_RETIRED,
        SS.quarantined: ErrorCode.EQUIPMENT_QUARANTINED,
        SS.awaiting_certificate: ErrorCode.CERT_MISSING,
    }.get(card.service_status, ErrorCode.EQUIPMENT_QUARANTINED)
    return CertCheckResult.not_usable, code


def _person(
    db: Session,
    p: Principal,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    at: datetime,
    qr: QrKind | None,
) -> CertCheckResponse:
    w = db.get(Worker, worker_id)
    dep = db.scalar(
        select(Deployment)
        .where(Deployment.worker_id == worker_id, Deployment.project_id == project_id)
        .limit(1)
    )
    if (
        w is None
        or dep is None
        or not _scope(db, p, project_id, dep.engagement_id, list(dep.site_ids or []))
    ):
        return _unknown(ErrorCode.OUT_OF_SCOPE, qr)
    audit.record(
        db,
        AuditAction.cert_check_view,
        p.actor(project_id),
        entity_type=EntityType.worker,
        entity_id=w.id,
        project_id=project_id,
    )
    card = person_card(db, w, project_id, at)
    ok = any(c.in_force for c in card.certificates)
    res = CertCheckResult.in_service if ok else CertCheckResult.not_usable
    return _resp(
        res,
        f"{len([c for c in card.certificates if c.in_force])} certificate(s) in force.",
        f"{len([c for c in card.certificates if c.in_force])} شهادة سارية.",
        qr_kind=qr,
        subject=CertCheckSubject.person,
        reason_code=None,
        person=card,
    )


# ---- gate EQ check (GE-1…GE-7) -------------------------------------------------------------------


def gate_check(
    db: Session, caller: Any, g: Any, zone: Zone | None, t: QrToken, body: Any, at: datetime
) -> Any:
    """Called by Phase 2 gate_check for QR kind EQ. Returns a GateCheckResponse."""
    from app.services.access import gates  # noqa: PLC0415
    from app.services.cert import deployments as dsvc  # noqa: PLC0415

    d, sc = _eq_subject(db, t)

    def log(
        result: GateResult, codes: list[str], ref_: str | None, dep: EquipmentDeployment | None
    ) -> Any:
        row = gates._log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.equipment_deployment,
            result,
            codes,
            at,
            qr_kind=QrKind.EQ,
            ref=ref_,
        )
        if dep is not None:
            row.equipment_deployment_id = dep.id
            row.engagement_id = dep.engagement_id
        db.flush()
        return row

    if d is None:
        # a scaffold sticker is not a gate subject; unknown subject for the gate
        v = gates.Verdict(deny=[G.TOKEN_UNKNOWN if sc is None else G.OUT_OF_SCOPE])
        row = log(GateResult.DENIED, v.codes(), t.printed_ref, None)
        return gates._response(db, row, g, zone, v)
    if d.project_id != g.project_id or not gates._scope_ok(caller, d.project_id, d.engagement_id):
        v = gates.Verdict(deny=[G.OUT_OF_SCOPE])
        row = log(GateResult.DENIED, v.codes(), t.printed_ref, None)
        return gates._response(db, row, g, zone, v)
    item = db.get(EquipmentItem, d.equipment_id)
    assert item is not None  # noqa: S101
    card = equipment_card(db, d, item, at)
    if body.direction == GateDirection.out:
        row = log(GateResult.EXIT_RECORDED, [], d.tag, d)
        return gates._response(db, row, g, zone, None, equipment=card)
    v = gates.Verdict()
    if t.status != QrTokenStatus.active or item.service_status == SS.retired:
        v.add(G.CREDENTIAL_REVOKED)
    elif item.service_status == SS.blacklisted:
        v.add(G.EQUIPMENT_BLACKLISTED)
    elif d.status in (DS.demobilised, DS.cancelled):
        v.add(G.EQUIPMENT_NOT_DEPLOYED)
    elif d.status == DS.planned:
        v.add(G.EQUIPMENT_NOT_APPROVED)
    else:
        eng = db.get(ProjectEngagement, d.engagement_id)
        con = db.get(Contractor, eng.contractor_id) if eng else None
        if con is not None and con.status == ContractorStatus.blacklisted:
            v.add(G.CONTRACTOR_BLACKLISTED)
        elif con is not None and con.status == ContractorStatus.suspended:
            s = acommon.settings(db, d.project_id)
            v.add(
                G.CONTRACTOR_SUSPENDED,
                warn=s.suspended_contractor_gate == SuspendedContractorGateMode.warn,
            )
        if item.service_status == SS.out_of_service:
            v.add(G.EQUIPMENT_OUT_OF_SERVICE)
        elif item.service_status in (SS.quarantined, SS.awaiting_certificate):
            v.add(G.EQUIPMENT_QUARANTINED)
        if not v.deny:
            ic = validity.current_line(db, item.id, at, d.project_id)
            if ic.ev.in_force and ic.ev.expiring:
                v.add(G.EXPIRING_7D, warn=True)
            elif not ic.ev.in_force:
                v.add(G.EQUIPMENT_QUARANTINED)
    if not v.deny:
        if d.status == DS.approved or (d.status == DS.on_site and not d.arrival_inspection_passed):
            v.add(G.ARRIVAL_INSPECTION_DUE, warn=True)
        if item.vehicle_id is not None and _vehicle_zone(db, g, zone):
            v.add(G.ALSO_SCAN_VEHICLE_STICKER, warn=True)
    row = log(v.result(), v.codes(), d.tag, d)
    if not v.deny and d.status == DS.approved:
        dsvc.arrive(db, d, at)
        card = equipment_card(db, d, item, at)
    return gates._response(db, row, g, zone, v, equipment=card)


def _vehicle_zone(db: Session, g: Any, zone: Zone | None) -> bool:
    """GE-4: the gate protects zones needing an AVP or access permit."""
    from app.services.access import profiles  # noqa: PLC0415

    zones = (
        [zone]
        if zone is not None and zone.id.int != 0
        else [z for z in (db.get(Zone, zid) for zid in g.protected_zone_ids or []) if z is not None]
    )
    if g.gate_type == GateType.site_gate and not zones:
        return False
    for z in zones:
        prof = profiles.ensure(db, z)
        if prof.avp_area_required is not None or prof.access_permit_required:
            return True
    return False
