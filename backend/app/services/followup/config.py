"""6f reference lists, project settings, client recipients, body directory and the notification rule
profile (spec 6f-incident-followup §3.1, §3.2, §3.10, §3.11, NR-3, NR-9, NR-10).

Settings and rules are edited by the HSE Manager only (218); "Allowed" ranges are enforced by the
schema; loosening values answer 422 SETTING_LOOSENING / RULE_LOOSENING; every change is audited and
applies to requirements created after it."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.followup_enums import (
    FuAckResponse,
    FuChannel,
    FuClientIdentity,
    FuDeadlineBasis,
    FuEffectResult,
    FuFieldSet,
    FuFiler,
    FuForm,
    FuLessonStatus,
    FuPackStatus,
    FuRequirementStatus,
    FuRuleSource,
    FuStage,
    FuTrigger,
    FuWaiverReason,
)
from app.core.hse_enums import ExternalBody
from app.models import FuRule
from app.schemas.followup import (
    FuDirectoryEntry,
    FuRecipient,
    FuReference,
    FuRefItem,
    FuRuleCreate,
    FuRuleList,
    FuRuleRead,
    FuRuleUpdate,
    FuSettingsRead,
    FuSettingsUpdate,
)
from app.services import audit
from app.services.followup import common as fc
from app.services.permissions import Principal

C = Capability

LABELS: dict[str, dict[str, tuple[str, str]]] = {
    "bodies": {
        "gosi": ("GOSI", "المؤسسة العامة للتأمينات الاجتماعية"),
        "mhrsd": ("MHRSD labour office", "مكتب العمل - وزارة الموارد البشرية"),
        "civil_defense": ("Civil Defense", "الدفاع المدني"),
        "police": ("Police", "الشرطة"),
        "gaca": ("GACA", "الهيئة العامة للطيران المدني"),
        "airport_operator": ("Airport operator", "مشغل المطار"),
        "client": ("Client / PMC", "العميل / الاستشاري"),
        "ncec": ("NCEC", "المركز الوطني للرقابة على الالتزام البيئي"),
    },
    "stages": {
        "verbal": ("Verbal notice", "إبلاغ شفهي"),
        "written": ("Written notification", "إخطار كتابي"),
        "interim": ("Interim report", "تقرير مرحلي"),
        "final": ("Final report", "تقرير نهائي"),
    },
    "triggers": {
        "recordable_contractor_case": (
            "Recordable contractor-worker case",
            "حالة مسجلة لعامل مقاول",
        ),
        "commuting_case": ("Commuting case", "حالة أثناء التنقل"),
        "fatality": ("Fatality", "وفاة"),
        "permanent_disability": ("Permanent disability", "عجز دائم"),
        "lti": ("Lost-time injury", "إصابة مضيعة للوقت"),
        "fire_explosion_do": ("Fire / explosion dangerous occurrence", "حريق / انفجار"),
        "any_do": ("Any dangerous occurrence", "أي حدث خطير"),
        "hipo": ("High-potential incident", "حادثة عالية الخطورة المحتملة"),
        "gaca_airside_flag": ("GACA airside flag", "مؤشر جانب الطيران لدى الهيئة"),
        "any_airside_flag": ("Any airside flag", "أي مؤشر جانب الطيران"),
        "env_ncec": ("Environmental incident (NCEC)", "حادثة بيئية (المركز الوطني)"),
        "env_airside": ("Environmental incident airside", "حادثة بيئية في جانب الطيران"),
        "any_recordable_case": ("Any recordable case", "أي حالة مسجلة"),
        "property_damage_ge_sar": ("Property damage ≥ SAR amount", "أضرار ممتلكات ≥ مبلغ"),
    },
    "forms": {
        "GOSI-WIR": ("GOSI work-injury data sheet", "بيانات بلاغ إصابة عمل"),
        "MHRSD-LTR": ("Letter to the labour office", "خطاب إلى مكتب العمل"),
        "CD-LTR": ("Letter to Civil Defense", "خطاب إلى الدفاع المدني"),
        "GACA-OCR": ("GACA occurrence report", "تقرير حدث للهيئة العامة للطيران المدني"),
        "AO-OCR": ("Airport operator occurrence report", "تقرير حدث لمشغل المطار"),
        "NCEC-EIR": ("Environmental incident report", "تقرير حادثة بيئية"),
        "CLIENT-FLASH": ("Client flash report", "تقرير أولي للعميل"),
        "CLIENT-INTERIM": ("Client interim report", "تقرير مرحلي للعميل"),
        "CLIENT-FINAL": ("Client final report", "تقرير نهائي للعميل"),
    },
    "field_sets": {
        "none": ("No identity", "بدون هوية"),
        "identity": ("Identity", "الهوية"),
        "identity_medical": ("Identity and injury details", "الهوية وتفاصيل الإصابة"),
    },
    "waiver_reasons": {
        "not_covered_by_gosi": ("Not covered by GOSI", "غير مشمول بالتأمينات"),
        "body_confirmed_not_required": ("Body confirmed not required", "أكدت الجهة عدم الحاجة"),
        "reported_by_other_party": ("Reported by another party", "أبلغ عنها طرف آخر"),
        "incident_reclassified": ("Incident reclassified", "أعيد تصنيف الحادثة"),
    },
    "requirement_statuses": {
        "due": ("Due", "مستحق"),
        "overdue": ("Overdue", "متأخر"),
        "submitted": ("Submitted", "تم الإرسال"),
        "acknowledged": ("Acknowledged", "تم الاستلام"),
        "waived": ("Waived", "معفى"),
        "not_required": ("Not required", "غير مطلوب"),
    },
    "pack_statuses": {
        "draft": ("Draft", "مسودة"),
        "approved": ("Approved", "معتمدة"),
        "submitted": ("Submitted", "مرسلة"),
        "superseded": ("Superseded", "مستبدلة"),
    },
    "channels": {
        "portal": ("Portal", "بوابة إلكترونية"),
        "email": ("Email", "بريد"),
        "hand_delivered": ("Hand delivered", "تسليم باليد"),
        "courier": ("Courier", "بريد سريع"),
        "phone_radio": ("Phone / radio", "هاتف/لاسلكي"),
        "meeting": ("Meeting", "اجتماع"),
    },
    "filers": {
        "main_contractor": ("Main contractor", "المقاول الرئيسي"),
        "employer_engagement": ("Employer of the injured worker", "صاحب العمل"),
        "airport_operator": ("Airport operator", "مشغل المطار"),
    },
    "lesson_statuses": {
        "draft": ("Draft", "مسودة"),
        "in_review": ("In review", "قيد المراجعة"),
        "published": ("Published", "منشور"),
        "archived": ("Archived", "مؤرشف"),
    },
    "ack_responses": {
        "will_brief": ("Will brief", "سيتم التوعية"),
        "not_applicable": ("Not applicable", "لا ينطبق"),
    },
    "effect_results": {
        "effective": ("Effective", "فعّال"),
        "partly_effective": ("Partly effective", "فعّال جزئياً"),
        "not_effective": ("Not effective", "غير فعّال"),
    },
    "client_identity": {
        "none": ("De-identified", "بدون هوية"),
        "name_and_trade": ("Name and trade", "الاسم والمهنة"),
    },
    "sources": {"statutory": ("Statutory", "نظامي"), "client": ("Client contract", "عقد العميل")},
    "deadline_basis": {
        "trigger": ("From the trigger", "من وقت تحقق الموجب"),
        "investigation_due": ("Investigation due date", "موعد التحقيق"),
    },
}  # fmt: skip
ENUMS: dict[str, Any] = {
    "bodies": ExternalBody, "stages": FuStage, "triggers": FuTrigger, "forms": FuForm,
    "field_sets": FuFieldSet, "waiver_reasons": FuWaiverReason,
    "requirement_statuses": FuRequirementStatus, "pack_statuses": FuPackStatus,
    "channels": FuChannel, "filers": FuFiler, "lesson_statuses": FuLessonStatus,
    "ack_responses": FuAckResponse, "effect_results": FuEffectResult,
    "client_identity": FuClientIdentity, "sources": FuRuleSource,
    "deadline_basis": FuDeadlineBasis,
}  # fmt: skip


def reference(db: Session, p: Principal) -> FuReference:
    out: dict[str, list[FuRefItem]] = {}
    for name, enum in ENUMS.items():
        lab = LABELS[name]
        out[name] = [
            FuRefItem(code=m.value, label_en=lab[m.value][0], label_ar=lab[m.value][1],
                      detail=(" · ".join(fc.FORMS[FuForm(m.value)][0])
                              if name == "forms" else None))
            for m in enum
        ]  # fmt: skip
    return FuReference(lists=out)


# ---- settings ------------------------------------------------------------------------------------


def settings_read(db: Session, project_id: uuid.UUID) -> FuSettingsRead:
    c = fc.cfg(db, project_id)
    v = c.v
    row = c.row
    return FuSettingsRead(
        project_id=project_id,
        followup_rules_from=c.rules_from,
        notification_alert_lead_hours=int(v["notification_alert_lead_hours"]),
        client_pack_identity=FuClientIdentity(v["client_pack_identity"]),
        client_identity_clause=row.client_identity_clause if row else None,
        lesson_required_levels=sorted(c.levels),
        lesson_publish_days=int(v["lesson_publish_days"]),
        lesson_ack_days=int(v["lesson_ack_days"]),
        lesson_effectiveness_days=int(v["lesson_effectiveness_days"]),
        followup_warning_pct=fc.s1(v["followup_warning_pct"]),
        lesson_ack_warning_pct=fc.s1(v["lesson_ack_warning_pct"]),
        client_recipients=[FuRecipient.model_validate(x) for x in (row.client_recipients if row
                                                                  else [])],
        body_directory=[FuDirectoryEntry.model_validate(x) for x in (row.body_directory if row
                                                                    else [])],
        signatory_role_en=row.signatory_role_en if row else None,
        signatory_role_ar=row.signatory_role_ar if row else None,
    )  # fmt: skip


def get_settings(db: Session, p: Principal, project_id: uuid.UUID) -> FuSettingsRead:
    fc.view_grant(db, p, project_id)
    return settings_read(db, project_id)


def _loose(k: str) -> Any:
    return fc.code_err(ErrorCode.SETTING_LOOSENING, f"{k} may only be tightened.",
                       f"لا يمكن تخفيف الإعداد {k}.", k)  # fmt: skip


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: FuSettingsUpdate
) -> FuSettingsRead:
    fc.project(db, p, project_id)
    p.require(project_id, C.followup_settings)
    data = body.model_dump(exclude_unset=True, mode="json")
    row = fc.settings_row(db, project_id)
    cur = fc.cfg(db, project_id)
    before = settings_read(db, project_id).model_dump(mode="json")
    vals = dict(row.values or {})
    today = fc.local_day()
    for k, new in data.items():
        if k == "followup_rules_from":
            d = date.fromisoformat(new) if new else None
            pr = fc.project(db, None, project_id)
            if d is None or (cur.rules_from is not None and d > cur.rules_from):
                raise _loose(k)
            if d > today or (pr.start_date is not None and d < pr.start_date):
                raise validation_error(k, "On or after the project start and not in the future.")
            row.followup_rules_from = d
            continue
        if k in ("client_recipients", "body_directory"):
            setattr(row, k, new or [])
            continue
        if k in ("signatory_role_en", "signatory_role_ar", "client_identity_clause"):
            setattr(row, k, new)
            continue
        old = cur.v[k]
        if k == "notification_alert_lead_hours" and int(new) < int(old):
            raise _loose(k)
        if k in ("lesson_publish_days", "lesson_ack_days") and int(new) > int(old):
            raise _loose(k)
        if k in ("followup_warning_pct", "lesson_ack_warning_pct") and Decimal(str(new)) < Decimal(
            str(old)
        ):
            raise _loose(k)
        if k == "lesson_required_levels":
            new = sorted(set(new))  # noqa: PLW2901
            if "L3" not in new or not set(new) <= {"L2", "L3"}:
                raise _loose(k)
        if k == "client_pack_identity" and new == FuClientIdentity.name_and_trade.value:
            clause = data.get("client_identity_clause") or row.client_identity_clause
            if not clause or len(clause.strip()) < 20:
                raise validation_error(
                    "client_identity_clause",
                    "Record the contract clause (≥ 20 characters) that allows naming (P6f-2).",
                )
        vals[k] = new
    if "client_recipients" in data and not data["client_recipients"]:
        from sqlalchemy import select  # noqa: PLC0415

        live = db.scalars(
            select(FuRule).where(
                FuRule.project_id == project_id,
                FuRule.source == FuRuleSource.client,
                FuRule.active.is_(True),
            )
        ).first()
        if live is not None:
            raise _recipient_error()
    row.values = vals
    row.updated_at = now()
    row.updated_by_user_id = p.user.id
    db.flush()
    fc.clear_cache(db)
    out = settings_read(db, project_id)
    after = out.model_dump(mode="json")
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(project_id),
        entity_type=EntityType.followup_settings,
        entity_id=project_id, project_id=project_id,
        before={k: before.get(k) for k in data}, after={k: after.get(k) for k in data},
    )  # fmt: skip
    return out


# ---- rules (§3.1, NR-3) --------------------------------------------------------------------------


def rule_read(r: FuRule) -> FuRuleRead:
    return FuRuleRead(
        id=r.id, project_id=r.project_id, rule_code=r.rule_code, body=r.body, stage=r.stage,
        source=r.source, triggers=[FuTrigger(t) for t in r.triggers],
        trigger_params=r.trigger_params or {}, deadline_hours=r.deadline_hours,
        deadline_basis=r.deadline_basis, form_code=FuForm(r.form_code) if r.form_code else None,
        filer=r.filer, active=r.active, updated_at=r.updated_at,
    )  # fmt: skip


def list_rules(db: Session, p: Principal, project_id: uuid.UUID) -> FuRuleList:
    fc.view_grant(db, p, project_id)
    return FuRuleList(items=[rule_read(r) for r in fc.ensure_profile(db, project_id)])


def _recipient_error() -> Any:
    return fc.code_err(
        ErrorCode.CLIENT_RECIPIENT_REQUIRED,
        "Add at least one client / PMC recipient before activating a client row (NR-9).",
        "أضف مستلماً واحداً على الأقل من العميل أو الاستشاري قبل تفعيل القاعدة.",
        "active",
    )


def _has_recipients(db: Session, project_id: uuid.UUID) -> bool:
    row = fc.cfg(db, project_id).row
    return bool(row and row.client_recipients)


def _snap(r: FuRule) -> dict[str, Any]:
    return {"triggers": list(r.triggers), "deadline_hours": r.deadline_hours,
            "active": r.active, "filer": r.filer.value, "form_code": r.form_code,
            "trigger_params": r.trigger_params}  # fmt: skip


def create_rule(db: Session, p: Principal, project_id: uuid.UUID, body: FuRuleCreate) -> FuRuleRead:
    fc.project(db, p, project_id)
    p.require(project_id, C.followup_settings)
    rules = fc.ensure_profile(db, project_id)
    if any(r.rule_code == body.rule_code for r in rules):
        raise validation_error("rule_code", "The rule code is already used on this project.")
    if body.active and not _has_recipients(db, project_id):
        raise _recipient_error()
    if body.deadline_basis == FuDeadlineBasis.trigger and body.deadline_hours is None:
        raise validation_error("deadline_hours", "Give the deadline in hours.")
    r = FuRule(
        project_id=project_id, rule_code=body.rule_code, body=ExternalBody.client,
        stage=body.stage, source=FuRuleSource.client,
        triggers=[t.value for t in dict.fromkeys(body.triggers)],
        trigger_params=body.trigger_params, deadline_hours=body.deadline_hours,
        deadline_basis=body.deadline_basis,
        form_code=body.form_code.value if body.form_code else None,
        filer=FuFiler.main_contractor, active=body.active, created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(r)
    db.flush()
    fc.record(db, p, AuditAction.create, EntityType.followup_rule, r, project_id)
    return rule_read(r)


def update_rule(db: Session, p: Principal, rule_id: uuid.UUID, body: FuRuleUpdate) -> FuRuleRead:
    r = db.get(FuRule, rule_id)
    if r is None or not p.can_see_project(r.project_id):
        raise not_found("Notification rule")
    p.require(r.project_id, C.followup_settings)
    data = body.model_dump(exclude_unset=True)
    before = _snap(r)

    def loose(field: str) -> Any:
        return fc.code_err(
            ErrorCode.RULE_LOOSENING,
            f"{r.rule_code} is a statutory row: it may only be tightened (NR-3).",
            f"القاعدة {r.rule_code} نظامية ولا يمكن إلا تشديدها.",
            field,
        )

    if r.source == FuRuleSource.statutory:
        if "deadline_hours" in data and (
            data["deadline_hours"] is None
            or (r.deadline_hours is not None and data["deadline_hours"] > r.deadline_hours)
        ):
            raise loose("deadline_hours")
        if "triggers" in data and not set(r.triggers) <= {t.value for t in data["triggers"]}:
            raise loose("triggers")
        if data.get("active") is False:
            raise loose("active")
        gaca_ok = r.rule_code == "GACA-W" and data.get("filer") in (
            FuFiler.main_contractor,
            FuFiler.airport_operator,
        )
        if "filer" in data and data["filer"] != r.filer and not gaca_ok:
            raise loose("filer")
        if "trigger_params" in data and r.trigger_params:
            raise loose("trigger_params")
    elif data.get("active") is True and not _has_recipients(db, r.project_id):
        raise _recipient_error()
    for k, v in data.items():
        if k == "triggers":
            r.triggers = [t.value for t in dict.fromkeys(v)]
        elif k == "form_code":
            r.form_code = v.value if v else None
        else:
            setattr(r, k, v)
    r.updated_by_user_id = p.user.id
    r.updated_at = now()
    db.flush()
    audit.record(
        db, AuditAction.update, p.actor(r.project_id), entity_type=EntityType.followup_rule,
        entity_id=r.id, project_id=r.project_id, before=before, after=_snap(r),
        details={"rule_code": r.rule_code},
    )  # fmt: skip
    return rule_read(r)
