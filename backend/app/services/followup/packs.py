"""Notification packs (spec 6f-incident-followup §3.4, §4.2, PK-1…PK-6, P6f-1…P6f-5).

A pack freezes the incident, case and investigation values of its field set (`snapshot`, PK-2).
The rendered file is a PDF (D-304; Arabic shaped right-to-left, the Umm al-Qura Hijri date next
to the Gregorian one, D-303) made with the 6g renderer; identity packs are stored in the encrypted
personal bucket and opened through signed URLs that live ≤ 5 minutes (P6f-4)."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.clock import now
from app.core.config import API_PREFIX, get_settings
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found
from app.core.followup_enums import (
    FuClientIdentity,
    FuFieldSet,
    FuForm,
    FuLessonStatus,
    FuPackAction,
    FuPackStatus,
)
from app.core.hse_enums import AttachmentOwner, ExternalBody
from app.models import (
    Attachment,
    CorrectiveAction,
    FuLesson,
    FuPack,
    FuRequirement,
    Incident,
    InjuryCase,
    Investigation,
    ProjectEngagement,
    Site,
    Zone,
)
from app.schemas.attachments import SignedUrlRead
from app.schemas.followup import (
    FuPackCreate,
    FuPackPage,
    FuPackRead,
    FuPackTransition,
    FuPackUpdate,
)
from app.services import audit
from app.services.followup import common as fc
from app.services.followup import requirements as rq
from app.services.permissions import Principal, forbidden_error

C = Capability
ET = EntityType
PS = FuPackStatus
GOVERNMENT = {ExternalBody.gosi, ExternalBody.mhrsd, ExternalBody.civil_defense,
              ExternalBody.police, ExternalBody.ncec, ExternalBody.najm}  # fmt: skip
CLIENT_FORMS = {FuForm.CLIENT_FLASH, FuForm.CLIENT_INTERIM, FuForm.CLIENT_FINAL}
IDENTITY_KEYS = ("person_name", "id_type", "id_number", "nationality")
MEDICAL_KEYS = ("body_part", "nature", "treated_at", "first_day_off", "days_off")


def _immutable() -> ApiError:
    return fc.err(409, ErrorCode.PACK_IMMUTABLE, "A Submitted pack cannot be changed.",
                  "لا يمكن تعديل حزمة مرسلة.")  # fmt: skip


def _field_set(form: FuForm) -> FuFieldSet:
    return FuFieldSet(fc.FORMS[form][1])


# ---- snapshot (PK-2, PK-3, P6f-2) ----------------------------------------------------------------


def _eng(db: Session, eng_id: uuid.UUID | None) -> dict[str, Any] | None:
    e = db.get(ProjectEngagement, eng_id) if eng_id else None
    if e is None or e.contractor is None:
        return None
    c = e.contractor
    return {"code": c.short_code, "name_en": c.legal_name_en, "name_ar": c.legal_name_ar,
            "cr_number": c.cr_number}  # fmt: skip


def _case_row(
    db: Session, c: InjuryCase, fs: FuFieldSet, form: FuForm, ident: FuClientIdentity
) -> dict[str, Any]:
    emp = _eng(db, c.employer_engagement_id)
    code = emp["code"] if emp else "—"
    trade = c.trade.value if c.trade else "—"
    row: dict[str, Any] = {
        "person_no": c.person_no,
        "label": f"Person {c.person_no} · {trade} · {code}",
        "label_ar": f"الشخص {c.person_no} · {trade} · {code}",
        "trade": trade,
        "employer": code,
        "category": c.category.value,
    }
    if form in CLIENT_FORMS:
        row["body_part"] = c.body_part.value if c.body_part else None
        row["days_off"] = _days_off(c)
        if ident == FuClientIdentity.name_and_trade and c.anonymised_at is None:
            row["person_name"] = c.person_name
            row["label"] = f"{c.person_name} · {trade} · {code}"
            row["label_ar"] = row["label"]
    if fs in (FuFieldSet.identity, FuFieldSet.identity_medical) and c.anonymised_at is None:
        row["person_name"] = c.person_name
        row["id_type"] = c.id_type.value if c.id_type else None
        num = None
        if c.id_number_enc:
            try:
                num = crypto.decrypt(c.id_number_enc)
            except Exception:
                num = c.id_number_masked
        row["id_number"] = num
        row["nationality"] = getattr(c.nationality, "value", c.nationality)
        row["occupation"] = trade
    if fs == FuFieldSet.identity_medical:
        row["body_part"] = c.body_part.value if c.body_part else None
        row["nature"] = c.nature.value if c.nature else None
        row["treated_at"] = c.treated_at.value if c.treated_at else None
        row["first_day_off"] = c.away_start_date.isoformat() if c.away_start_date else None
        row["days_off"] = _days_off(c)
    return row


def _days_off(c: InjuryCase) -> int | None:
    if c.away_start_date is None:
        return None
    end = c.rtw_date or fc.local_day()
    return max((end - c.away_start_date).days, 0)


def build_snapshot(
    db: Session, req: FuRequirement, inc: Incident, form: FuForm, fs: FuFieldSet
) -> dict[str, Any]:
    pid = inc.project_id
    site = db.get(Site, inc.site_id)
    zone = db.get(Zone, inc.zone_id) if inc.zone_id else None
    loc = fc.to_local(inc.occurred_at)
    ident = FuClientIdentity(fc.cfg(db, pid)["client_pack_identity"])
    cases = list(
        db.scalars(
            select(InjuryCase)
            .where(InjuryCase.incident_id == inc.id)
            .order_by(InjuryCase.person_no)
        )
    )
    if req.case_ids:
        cases = [c for c in cases if c.id in req.case_ids]
    snap: dict[str, Any] = {
        "incident_ref": inc.ref,
        "occurred_date": loc.date().isoformat(),
        "occurred_time": f"{loc:%H:%M}",
        "site": site.code if site else None,
        "location": " · ".join(x for x in [zone.code if zone else None, inc.location_detail] if x),
        "title": inc.title,
        "activity": inc.activity.value if inc.activity else None,
        "incident_types": list(inc.incident_types or []),
        "airside_flags": list(inc.airside_flags or []),
        "do_category": inc.do_category.value if inc.do_category else None,
        "actual_severity": inc.actual_severity,
        "potential_severity": inc.potential_severity,
        "description": fc.redact(db, inc, inc.description),
        "immediate_actions": fc.redact(db, inc, inc.immediate_actions),
        "responsible": (_eng(db, inc.responsible_engagement_id) or {}).get("code"),
        "cases": [_case_row(db, c, fs, form, ident) for c in cases],
    }
    if form == FuForm.GOSI_WIR:
        emp = _eng(db, req.filer_engagement_id) or {}
        snap["employer"] = emp
    if form == FuForm.CLIENT_FINAL:
        inv = db.get(Investigation, inc.id)
        snap["root_cause_codes"] = [r.get("code") for r in (inv.root_causes or [])] if inv else []
        snap["causes"] = fc.redact(db, inc, inv.immediate_causes) if inv else None
        snap["corrective_actions"] = [
            {"ref": ca.ref, "control_level": ca.control_level.value, "status": ca.status.value}
            for ca in db.scalars(
                select(CorrectiveAction)
                .where(CorrectiveAction.source_id == inc.id)
                .order_by(CorrectiveAction.ref)
            )
        ]
        les = db.scalars(
            select(FuLesson).where(
                FuLesson.incident_id == inc.id, FuLesson.status == FuLessonStatus.published
            )
        ).first()
        snap["lesson_no"] = les.lesson_no if les else None
    return snap


def _changed(db: Session, pk: FuPack, req: FuRequirement, inc: Incident) -> bool:
    if pk.identity_deleted_at is not None:
        return False
    fresh = build_snapshot(db, req, inc, FuForm(pk.form_code), pk.field_set)
    return fresh != (pk.snapshot or {})


# ---- access --------------------------------------------------------------------------------------


def _identity_ok(
    p: Principal, req: FuRequirement, inc: Incident, fs: FuFieldSet, form: FuForm
) -> bool:
    if fs == FuFieldSet.none:
        return True
    eng = req.filer_engagement_id or inc.responsible_engagement_id
    g29 = p.grant(req.project_id, C.injury_identity_view)
    if g29 is None or not g29.covers_site(inc.site_id) or not g29.covers_engagement(eng):
        return False
    if fs == FuFieldSet.identity:
        return True
    g30 = p.grant(req.project_id, C.injury_medical_view)
    if g30 is not None and g30.covers_engagement(eng):
        return True
    # PK-1 exception: a Contractor HSE Rep with 29 in C scope may generate GOSI-WIR for an
    # employer engagement in that scope (limited medical part)
    sc = p.projects.get(req.project_id)
    return form == FuForm.GOSI_WIR and sc is not None and Role.contractor_hse_rep in sc.roles


def _get(db: Session, p: Principal, pack_id: uuid.UUID) -> tuple[FuPack, FuRequirement, Incident]:
    pk = db.get(FuPack, pack_id)
    if pk is None or not p.can_see_project(pk.project_id):
        raise not_found("Notification pack")
    if fc.is_viewer(p, pk.project_id):
        raise forbidden_error("Viewer / Client never sees packs (P6f-5).")
    req, inc = rq.get_req(db, p, pk.requirement_id)
    return pk, req, inc


def to_read(db: Session, p: Principal, pk: FuPack, req: FuRequirement, inc: Incident) -> FuPackRead:
    form = FuForm(pk.form_code)
    visible = _identity_ok(p, req, inc, pk.field_set, form)
    return FuPackRead(
        id=pk.id, pack_no=pk.pack_no, project_id=pk.project_id, requirement_id=pk.requirement_id,
        incident_ref=inc.ref, body=req.body, stage=req.stage, version=pk.version, form_code=form,
        field_set=pk.field_set, languages=list(pk.languages or []),
        snapshot=pk.snapshot if visible else None,
        narrative_en=pk.narrative_en if visible or pk.field_set == FuFieldSet.none else None,
        narrative_ar=pk.narrative_ar if visible or pk.field_set == FuFieldSet.none else None,
        extra_fields=pk.extra_fields if visible else None, has_file=pk.file_id is not None,
        prepared_by=fc.user_ref(db, pk.created_by_user_id),
        approved_by=fc.user_ref(db, pk.approved_by_user_id), approved_at=pk.approved_at,
        status=pk.status,
        incident_changed=pk.status != PS.superseded and _changed(db, pk, req, inc),
        identity_deleted=pk.identity_deleted_at is not None,
        warnings=fc.p18_warnings({"narrative_en": pk.narrative_en,
                                  "narrative_ar": pk.narrative_ar}),
        created_at=pk.created_at,
    )  # fmt: skip


def _audit_read(db: Session, p: Principal, pk: FuPack, req: FuRequirement, what: str) -> None:
    if pk.field_set != FuFieldSet.none:
        fields = list(IDENTITY_KEYS) + (
            list(MEDICAL_KEYS) if pk.field_set == FuFieldSet.identity_medical else [])  # fmt: skip
        audit.record(db, AuditAction.sensitive_field_read, p.actor(pk.project_id),
                     entity_type=ET.followup_pack, entity_id=pk.id, project_id=pk.project_id,
                     fields_read=fields, details={"what": what})  # fmt: skip
    audit.record(db, AuditAction.export, p.actor(pk.project_id), entity_type=ET.followup_pack,
                 entity_id=pk.id, project_id=pk.project_id,
                 details={"purpose": req.body.value, "pack_no": pk.pack_no,
                          "what": what})  # fmt: skip


# ---- generate / edit / transitions ---------------------------------------------------------------


def _check_texts(
    db: Session, inc: Incident, fs: FuFieldSet, en: str | None, ar: str | None
) -> None:
    if fs == FuFieldSet.none:
        fc.check_identity(db, inc.id, {"narrative_en": en, "narrative_ar": ar})


def generate(db: Session, p: Principal, req_id: uuid.UUID, body: FuPackCreate) -> FuPackRead:
    req, inc = rq.get_req(db, p, req_id, C.followup_record)
    if not req.form_code:
        raise fc.code_err(ErrorCode.VALIDATION_ERROR, "Verbal stages have no pack.",
                          "لا توجد حزمة للمرحلة الشفهية.", "requirement_id")  # fmt: skip
    form = FuForm(req.form_code)
    fs = _field_set(form)
    if not _identity_ok(p, req, inc, fs, form):
        raise forbidden_error("This pack holds identity data: capability 29 (and 30) needed.")
    if form == FuForm.CLIENT_FINAL:
        inv = db.get(Investigation, inc.id)
        if inv is None or inv.approved_at is None:
            raise fc.code_err(
                ErrorCode.INVESTIGATION_NOT_APPROVED,
                "The final client report needs the investigation approved (PK-5).",
                "يتطلب التقرير النهائي اعتماد التحقيق.",
            )
    old = rq._current_pack(db, req.id)
    if old is not None and old.status == PS.submitted:
        raise _immutable()
    snap = build_snapshot(db, req, inc, form, fs)
    default = " ".join(x for x in [snap.get("description"), snap.get("immediate_actions")] if x)
    if form == FuForm.CLIENT_FINAL and snap.get("causes"):
        default = f"{default} {snap['causes']}".strip()
    en = body.narrative_en if body.narrative_en is not None else (default or None)
    ar = body.narrative_ar
    _check_texts(db, inc, fs, en, ar)
    langs = list(fc.FORMS[form][0])
    if body.languages and form in CLIENT_FORMS:
        langs = sorted({x for x in body.languages if x in ("en", "ar")} | set(langs))
    year = fc.local_day().year
    from app.services.hse_common import next_seq  # noqa: PLC0415

    seq = next_seq(db, FuPack, req.project_id, year)
    pk = FuPack(
        id=uuid.uuid4(),
        pack_no=f"NP-{fc.pcode(db, req.project_id)}-{year}-{seq:04d}", year=year, seq=seq,
        project_id=req.project_id, requirement_id=req.id,
        version=(old.version + 1) if old is not None else 1, form_code=form.value, field_set=fs,
        languages=langs, snapshot=snap, narrative_en=en, narrative_ar=ar,
        extra_fields=body.extra_fields or {}, status=PS.draft, created_by_user_id=p.user.id,
        alerts_sent=[],
    )  # fmt: skip
    if old is not None:
        old.status = PS.superseded
        old.updated_by_user_id = p.user.id
    db.add(pk)
    db.flush()
    fc.record(db, p, AuditAction.create, ET.followup_pack, pk, pk.project_id,
              details={"form": form.value, "version": pk.version})  # fmt: skip
    _audit_read(db, p, pk, req, "generate")
    return to_read(db, p, pk, req, inc)


def list_packs(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[PS] | None,
    req_id: uuid.UUID | None,
    page: int,
    size: int,
) -> FuPackPage:
    g = fc.view_grant(db, p, project_id)
    if fc.is_viewer(p, project_id):
        raise forbidden_error("Viewer / Client never sees packs (P6f-5).")
    stmt = select(FuPack).where(FuPack.project_id == project_id)
    if statuses:
        stmt = stmt.where(FuPack.status.in_(statuses))
    if req_id:
        stmt = stmt.where(FuPack.requirement_id == req_id)
    out = []
    for pk in db.scalars(stmt.order_by(FuPack.created_at.desc())):
        req = db.get(FuRequirement, pk.requirement_id)
        inc = db.get(Incident, req.incident_id) if req else None
        if req is None or inc is None or not rq.scope_ok(g, inc, req):
            continue
        out.append((pk, req, inc))
    items = [to_read(db, p, *x) for x in out[(page - 1) * size : page * size]]
    return FuPackPage(items=items, total=len(out), page=page, page_size=size)


def read_pack(db: Session, p: Principal, pack_id: uuid.UUID) -> FuPackRead:
    pk, req, inc = _get(db, p, pack_id)
    if pk.field_set != FuFieldSet.none and _identity_ok(p, req, inc, pk.field_set,
                                                        FuForm(pk.form_code)):  # fmt: skip
        _audit_read(db, p, pk, req, "view")
    return to_read(db, p, pk, req, inc)


def update_pack(db: Session, p: Principal, pack_id: uuid.UUID, body: FuPackUpdate) -> FuPackRead:
    pk, req, inc = _get(db, p, pack_id)
    rq.get_req(db, p, pk.requirement_id, C.followup_record)
    if pk.status != PS.draft:
        raise _immutable()
    data = body.model_dump(exclude_unset=True)
    en = data.get("narrative_en", pk.narrative_en)
    ar = data.get("narrative_ar", pk.narrative_ar)
    _check_texts(db, inc, pk.field_set, en, ar)
    for k, v in data.items():
        setattr(pk, k, v if v is not None or k != "extra_fields" else {})
    pk.updated_by_user_id = p.user.id
    pk.updated_at = now()
    db.flush()
    return to_read(db, p, pk, req, inc)


def transition_pack(
    db: Session, p: Principal, pack_id: uuid.UUID, body: FuPackTransition
) -> FuPackRead:
    pk, req, inc = _get(db, p, pack_id)
    rq.get_req(db, p, pk.requirement_id, C.followup_approve)
    sc = p.projects.get(pk.project_id)
    if (
        not p.is_manager
        and sc is not None
        and Role.contractor_hse_rep in sc.roles
        and not (sc.roles & {Role.hse_officer})
    ):
        g = p.grant(pk.project_id, C.followup_approve)
        if (
            FuForm(pk.form_code) != FuForm.GOSI_WIR
            or g is None
            or not g.covers_engagement(req.filer_engagement_id)
        ):
            raise forbidden_error("Contractor HSE Reps approve only GOSI packs of their scope.")
    before = {"status": pk.status.value}
    if body.action == FuPackAction.approve:
        if pk.status != PS.draft:
            from app.services.common import invalid_transition  # noqa: PLC0415

            raise invalid_transition("Pack", pk.status, PS.approved)
        pk.status = PS.approved
        pk.approved_by_user_id = p.user.id
        pk.approved_at = now()
        render(db, pk, req, inc, p.user.id)
    else:
        if pk.status == PS.submitted:
            raise _immutable()
        if pk.status != PS.approved:
            from app.services.common import invalid_transition  # noqa: PLC0415

            raise invalid_transition("Pack", pk.status, PS.draft)
        pk.status = PS.draft
        pk.approved_by_user_id = None
        pk.approved_at = None
    pk.updated_by_user_id = p.user.id
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.followup_pack, pk, pk.project_id, before=before)
    return to_read(db, p, pk, req, inc)


# ---- rendering (PK-4) ----------------------------------------------------------------------------


FORM_TITLES: dict[FuForm, tuple[str, str]] = {
    FuForm.GOSI_WIR: ("Work injury report (GOSI)",
                      "بلاغ إصابة عمل (المؤسسة العامة للتأمينات الاجتماعية)"),
    FuForm.MHRSD_LTR: ("Notification letter (Ministry of Human Resources)",
                       "خطاب إشعار (وزارة الموارد البشرية والتنمية الاجتماعية)"),
    FuForm.CD_LTR: ("Notification letter (Civil Defense)", "خطاب إشعار (الدفاع المدني)"),
    FuForm.GACA_OCR: ("Occurrence report (GACA)", "تقرير حادثة (الهيئة العامة للطيران المدني)"),
    FuForm.AO_OCR: ("Occurrence report (airport operator)", "تقرير حادثة (مشغّل المطار)"),
    FuForm.NCEC_EIR: ("Environmental incident report (NCEC)",
                      "تقرير حادث بيئي (المركز الوطني للرقابة على الالتزام البيئي)"),
    FuForm.CLIENT_FLASH: ("Client flash report", "التقرير الأولي للعميل"),
    FuForm.CLIENT_INTERIM: ("Client interim report", "التقرير المرحلي للعميل"),
    FuForm.CLIENT_FINAL: ("Client final report", "التقرير النهائي للعميل"),
}  # fmt: skip
FIELD_LABELS: dict[str, tuple[str, str]] = {
    "incident_ref": ("Incident ref.", "مرجع الحادث"),
    "occurred_date": ("Date of incident", "تاريخ الحادث"),
    "occurred_time": ("Time", "الوقت"),
    "site": ("Site", "الموقع"),
    "location": ("Location", "المكان"),
    "title": ("Title", "العنوان"),
    "activity": ("Activity", "النشاط"),
    "airside_flags": ("Airside", "الجانب الجوي"),
    "do_category": ("Dangerous occurrence category", "فئة الحدث الخطر"),
    "potential_severity": ("Potential severity", "الخطورة المحتملة"),
    "root_cause_codes": ("Root causes", "الأسباب الجذرية"),
    "corrective_actions": ("Corrective actions", "الإجراءات التصحيحية"),
    "lesson_no": ("Lesson", "الدرس المستفاد"),
    "employer": ("Employer", "صاحب العمل"),
    "person_no": ("Person no.", "رقم الشخص"),
    "label": ("Person", "الشخص"),
    "trade": ("Trade", "المهنة"),
    "category": ("Category", "التصنيف"),
    "body_part": ("Body part", "الجزء المصاب"),
    "days_off": ("Days off work", "أيام الانقطاع عن العمل"),
    "person_name": ("Name", "الاسم"),
    "id_type": ("ID type", "نوع الهوية"),
    "id_number": ("ID number", "رقم الهوية"),
    "nationality": ("Nationality", "الجنسية"),
    "occupation": ("Occupation", "المهنة"),
    "nature": ("Nature of injury", "طبيعة الإصابة"),
    "treated_at": ("Treated at", "مكان العلاج"),
    "first_day_off": ("First day off", "أول يوم انقطاع"),
}
PACK_FIELDS = ("incident_ref", "occurred_date", "occurred_time", "site", "location", "title",
               "activity", "airside_flags", "do_category", "potential_severity")  # fmt: skip
FINAL_FIELDS = ("root_cause_codes", "corrective_actions", "lesson_no", "employer")


def _value(v: Any) -> str:
    if v is None or v in ("", []):
        return "—"
    if isinstance(v, list):
        return ", ".join(_value(x) for x in v)
    if isinstance(v, dict):
        return " · ".join(f"{k}: {_value(x)}" for k, x in v.items() if x not in (None, ""))
    return str(v)


def _lines(items: list[tuple[str, Any]]) -> tuple[list[str], list[str]]:
    from app.services.scorecard import render  # noqa: PLC0415

    en, ar = [], []
    for key, v in items:
        lab_en, lab_ar = FIELD_LABELS.get(key, (key, key))
        val = _value(v)
        en.append(f"{lab_en}: {val}")
        ar.append(f"{lab_ar}: {render.ar_value(val)}")
    return en, ar


def render_doc(db: Session, pk: FuPack, req: FuRequirement, inc: Incident) -> Any:
    """PK-4 pack as a `render.Doc` (D-304): reference, date with its Umm al-Qura Hijri date
    (D-303), addressee, the frozen snapshot, narrative and signatory."""
    import hashlib  # noqa: PLC0415
    import json  # noqa: PLC0415

    from app.core.hijri import hijri_ar, hijri_en  # noqa: PLC0415
    from app.services.scorecard import render  # noqa: PLC0415

    c = fc.cfg(db, pk.project_id)
    row = c.row
    form = FuForm(pk.form_code)
    snap = pk.snapshot or {}
    today = fc.local_day()
    addressee = next(
        (d for d in (row.body_directory if row else []) if d.get("body") == req.body.value), None
    )
    recips = row.client_recipients if row and req.body == ExternalBody.client else []
    control: list[tuple[str, ...]] = [
        ("Reference", "المرجع", f"{pk.pack_no} · v{pk.version}"),
        ("Date", "التاريخ", today.isoformat()),
        ("Date (Hijri, Umm al-Qura)", "التاريخ الهجري، أم القرى", hijri_en(today), hijri_ar(today)),
    ]  # fmt: skip
    if addressee:
        office_en = _value(addressee.get("office_name_en"))
        office_ar = _value(addressee.get("office_name_ar") or addressee.get("office_name_en"))
        control.append(("To", "إلى", office_en, office_ar))
    for r in recips:
        org_en = f"{_value(r.get('organisation_en'))} ({_value(r.get('role'))})"
        org_ar = _value(r.get("organisation_ar") or r.get("organisation_en"))
        control.append(("To", "إلى", org_en, org_ar))
    det_en, det_ar = _lines([(k, snap.get(k)) for k in PACK_FIELDS])
    sections = [render.Section(key="incident", title_en="Incident", title_ar="الحادث",
                               paragraphs_en=det_en, paragraphs_ar=det_ar)]  # fmt: skip
    for case in snap.get("cases", []):
        items = [(k, v) for k, v in case.items() if k not in ("label", "label_ar", "person_no")]
        c_en, c_ar = _lines(items)
        sections.append(render.Section(
            key=f"person-{case.get('person_no')}", title_en=_value(case.get("label")),
            title_ar=_value(case.get("label_ar") or case.get("label")),
            paragraphs_en=c_en, paragraphs_ar=c_ar))  # fmt: skip
    more = [(k, snap.get(k)) for k in FINAL_FIELDS if k in snap]
    more += [(str(k), v) for k, v in (pk.extra_fields or {}).items()]
    if more:
        m_en, m_ar = _lines(more)
        sections.append(render.Section(key="more", title_en="Further details",
                                       title_ar="تفاصيل إضافية", paragraphs_en=m_en,
                                       paragraphs_ar=m_ar))  # fmt: skip
    nar_en = pk.narrative_en or pk.narrative_ar or "—"
    nar_ar = pk.narrative_ar or pk.narrative_en or "—"
    sections.append(render.Section(key="narrative", title_en="Narrative", title_ar="السرد",
                                   paragraphs_en=[nar_en], paragraphs_ar=[nar_ar]))  # fmt: skip
    sig_en = (row.signatory_role_en if row else None) or "Project HSE Manager"
    sig_ar = (row.signatory_role_ar if row else None) or "مدير السلامة للمشروع"
    sections.append(render.Section(
        key="signatory", title_en="Signatory", title_ar="التوقيع",
        paragraphs_en=[sig_en, "Prepared by: HSE Officer"],
        paragraphs_ar=[sig_ar, "أعدّها: مسؤول السلامة"]))  # fmt: skip
    title_en, title_ar = FORM_TITLES.get(form, (form.value, form.value))
    digest = hashlib.sha256(json.dumps([snap, pk.narrative_en, pk.narrative_ar,
                                        pk.extra_fields], default=str, sort_keys=True).encode()
                            ).hexdigest()  # fmt: skip
    return render.Doc(doc_no=pk.pack_no, revision=pk.version, title_en=title_en,
                      title_ar=title_ar, snapshot_hash=digest, control=control,
                      sections=sections)  # fmt: skip


def pack_languages(pk: FuPack) -> list[str]:
    """Government forms are Arabic, with the English translation as an annex when asked for;
    client and aviation forms are English then Arabic."""
    form = FuForm(pk.form_code)
    if fc.FORMS[form][0] == ["ar"]:
        return ["ar", "en"] if "en" in (pk.languages or []) else ["ar"]
    return ["en", "ar"]


def render_pdf(db: Session, pk: FuPack, req: FuRequirement, inc: Incident) -> bytes:
    from app.services.scorecard import render  # noqa: PLC0415

    return render.pdf(render_doc(db, pk, req, inc), pack_languages(pk))


def render(db: Session, pk: FuPack, req: FuRequirement, inc: Incident, user_id: uuid.UUID) -> None:
    owner = (AttachmentOwner.fu_pack_file if pk.field_set == FuFieldSet.none
             else AttachmentOwner.fu_pack_identity_file)  # fmt: skip
    if pk.file_id:
        old = db.get(Attachment, pk.file_id)
        pk.file_id = None
        db.flush()
        if old is not None:
            from app.services import attachments  # noqa: PLC0415

            attachments.erase(db, old)
    pk.file_id = fc.store_bytes(
        db, owner, pk.id, pk.project_id, f"{pk.pack_no}-v{pk.version}.pdf",
        render_pdf(db, pk, req, inc), "application/pdf", user_id,
    )  # fmt: skip


def file_url(db: Session, p: Principal, pack_id: uuid.UUID) -> SignedUrlRead:
    pk, req, inc = _get(db, p, pack_id)
    if not _identity_ok(p, req, inc, pk.field_set, FuForm(pk.form_code)):
        raise forbidden_error("This pack holds identity data: capability 29 (and 30) needed.")
    if pk.file_id is None:
        raise fc.err(409, ErrorCode.INVALID_TRANSITION, "The pack is rendered at approval.",
                     "تُنشأ الحزمة عند الاعتماد.")  # fmt: skip
    ttl = 300 if pk.field_set != FuFieldSet.none else 900
    expires = int(time.time()) + ttl
    sig = crypto.sign(f"{pk.file_id}:{expires}", get_settings().attachment_url_secret)
    _audit_read(db, p, pk, req, "download")
    return SignedUrlRead(
        url=f"{API_PREFIX}/attachments/{pk.file_id}/content?expires={expires}&signature={sig}",
        expires_at=datetime.fromtimestamp(expires, tz=fc.to_local(now()).tzinfo),
    )


# ---- P6f-4: identity removal at anonymisation ----------------------------------------------------


def purge_identity(db: Session) -> int:
    """Identity packs of anonymised cases: file and identity snapshot fields deleted; pack_no,
    body, stage, dates and submission references remain."""
    n = 0
    for pk in db.scalars(
        select(FuPack).where(
            FuPack.field_set != FuFieldSet.none, FuPack.identity_deleted_at.is_(None)
        )
    ):
        req = db.get(FuRequirement, pk.requirement_id)
        if req is None:
            continue
        cases = list(
            db.scalars(select(InjuryCase).where(InjuryCase.incident_id == req.incident_id))
        )
        if req.case_ids:
            cases = [c for c in cases if c.id in req.case_ids]
        if not cases or not all(c.anonymised_at is not None for c in cases):
            continue
        snap = dict(pk.snapshot or {})
        snap["cases"] = [
            {k: v for k, v in c.items() if k not in IDENTITY_KEYS + MEDICAL_KEYS + ("occupation",)}
            for c in snap.get("cases", [])
        ]
        pk.snapshot = snap
        pk.extra_fields = {}
        pk.narrative_en = None
        pk.narrative_ar = None
        if pk.file_id:
            a = db.get(Attachment, pk.file_id)
            pk.file_id = None
            db.flush()
            if a is not None:
                from app.services import attachments  # noqa: PLC0415

                attachments.erase(db, a)
        pk.identity_deleted_at = now()
        audit.record(db, AuditAction.update, audit.SYSTEM, entity_type=ET.followup_pack,
                     entity_id=pk.id, project_id=pk.project_id,
                     details={"identity_deleted": pk.pack_no})  # fmt: skip
        n += 1
    return n


def approval_alerts(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    """§7: pack awaiting approval > 4 h → 217 holders in scope, once."""
    from datetime import timedelta  # noqa: PLC0415

    n = 0
    for pk in db.scalars(
        select(FuPack).where(
            FuPack.project_id == project_id,
            FuPack.status == PS.draft,
            FuPack.created_at <= at - timedelta(hours=4),
        )
    ):
        if not fc.once(db, f"fu:pack:{pk.id}:approval"):
            continue
        req = db.get(FuRequirement, pk.requirement_id)
        who = set(fc.officers(db, project_id))
        if req is not None and FuForm(pk.form_code) == FuForm.GOSI_WIR:
            who |= fc.reps(db, project_id, req.filer_engagement_id)
        n += fc.send(db, who, NotificationKind.followup_pack_approval,
                     f"{pk.pack_no} is waiting for approval", f"{pk.pack_no} بانتظار الاعتماد",
                     project_id, ET.followup_pack, pk.id)  # fmt: skip
    return n
