"""Helpers shared by the Phase 6f services (spec 6f-incident-followup): settings (§3.10 defaults
merged over the stored values), the default rule profile (§3.11), files, Arabic normalisation
(LL-5), the P6f-3 identity check, PK-3 redaction and the Umm al-Qura date (PK-4)."""

from __future__ import annotations

import base64
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.followup_enums import FuDeadlineBasis, FuFiler, FuForm, FuRuleSource, FuStage
from app.core.followup_enums import FuTrigger as T
from app.core.hse_enums import AttachmentOwner, ExternalBody, InvestigationLevel
from app.models import (
    FuRule,
    FuSettings,
    Incident,
    InjuryCase,
    Project,
    ProjectEngagement,
)
from app.services.env.common import (
    err,
    local_day,
    managers,
    need,
    officers,
    once,
    pcode,
    project,
    reason,
    record,
    reps,
    send,
    site_engineers,
    to_local,
    user_ref,
)
from app.services.permissions import Grant, Principal

__all__ = [
    "err",
    "local_day",
    "managers",
    "need",
    "officers",
    "once",
    "pcode",
    "project",
    "reason",
    "record",
    "reps",
    "send",
    "site_engineers",
    "to_local",
    "user_ref",
]

C = Capability
D = Decimal
B = ExternalBody
S = FuStage

DEFAULTS: dict[str, Any] = {
    "notification_alert_lead_hours": 24,
    "client_pack_identity": "none",
    "lesson_required_levels": ["L3"],
    "lesson_publish_days": 14,
    "lesson_ack_days": 7,
    "lesson_effectiveness_days": 90,
    "followup_warning_pct": "95.0",
    "lesson_ack_warning_pct": "85.0",
}


@dataclass
class Cfg:
    project_id: uuid.UUID
    rules_from: date | None
    v: dict[str, Any]
    row: FuSettings | None

    def __getitem__(self, k: str) -> Any:
        return self.v[k]

    def dec(self, k: str) -> Decimal:
        return D(str(self.v[k]))

    @property
    def levels(self) -> set[InvestigationLevel]:
        return {InvestigationLevel(x) for x in self.v["lesson_required_levels"]}


def settings_row(db: Session, project_id: uuid.UUID) -> FuSettings:
    s = db.get(FuSettings, project_id)
    if s is None:
        s = FuSettings(project_id=project_id, values={}, client_recipients=[], body_directory=[])
        db.add(s)
        db.flush()
    return s


def cfg(db: Session, project_id: uuid.UUID) -> Cfg:
    cache: dict[uuid.UUID, Cfg] = db.info.setdefault("fu_cfg", {})
    if project_id not in cache:
        s = db.get(FuSettings, project_id)
        cache[project_id] = Cfg(
            project_id,
            s.followup_rules_from if s else None,
            {**DEFAULTS, **((s.values or {}) if s else {})},
            s,
        )
    return cache[project_id]


def clear_cache(db: Session) -> None:
    db.info.pop("fu_cfg", None)


def under_profile(db: Session, inc: Incident) -> bool:
    """NR-1: the incident occurred on or after the project's `followup_rules_from`."""
    c = cfg(db, inc.project_id)
    return c.rules_from is not None and inc.occurred_date >= c.rules_from


def q1(v: Decimal | None) -> Decimal | None:
    return None if v is None else D(v).quantize(D("0.1"), rounding=ROUND_HALF_UP)


def s1(v: Any) -> str:
    return str(q1(D(str(v))))


def code_err(code: ErrorCode, en: str, ar: str, field: str | None = None, **meta: Any) -> ApiError:
    return err(422, code, en, ar, field, **meta)


def view_grant(db: Session, p: Principal, project_id: uuid.UUID) -> Grant:
    project(db, p, project_id)
    return need(p, project_id, C.followup_view, write=False)


def is_viewer(p: Principal, project_id: uuid.UUID) -> bool:
    if p.is_manager:
        return False
    sc = p.projects.get(project_id)
    return sc is not None and sc.read_only


def eng_code(db: Session, eng_id: uuid.UUID | None) -> str | None:
    e = db.get(ProjectEngagement, eng_id) if eng_id else None
    return e.contractor.short_code if e is not None and e.contractor is not None else None


def descendants(db: Session, eng_id: uuid.UUID) -> set[uuid.UUID]:
    from app.services.permissions import engagement_descendants  # noqa: PLC0415

    return engagement_descendants(db, eng_id)


def project_codes(db: Session, ids: list[uuid.UUID]) -> list[str]:
    out = []
    for i in ids:
        pr = db.get(Project, i)
        if pr is not None:
            out.append(pr.code)
    return out


# ---- default profile (§3.11) ---------------------------------------------------------------------

# rule_code → (body, stage, triggers, hours, basis, form, filer)
STATUTORY: dict[str, tuple[B, S, list[T], int | None, FuForm | None, FuFiler]] = {
    "GOSI-W": (B.gosi, S.written, [T.recordable_contractor_case, T.commuting_case], 72,
               FuForm.GOSI_WIR, FuFiler.employer_engagement),
    "MHRSD-F": (B.mhrsd, S.written, [T.fatality], 24, FuForm.MHRSD_LTR, FuFiler.main_contractor),
    "MHRSD-PD": (B.mhrsd, S.written, [T.permanent_disability], 72, FuForm.MHRSD_LTR,
                 FuFiler.main_contractor),
    "POL-V": (B.police, S.verbal, [T.fatality], 1, None, FuFiler.main_contractor),
    "CD-V": (B.civil_defense, S.verbal, [T.fire_explosion_do], 1, None, FuFiler.main_contractor),
    "CD-W": (B.civil_defense, S.written, [T.fire_explosion_do], 24, FuForm.CD_LTR,
             FuFiler.main_contractor),
    "GACA-W": (B.gaca, S.written, [T.gaca_airside_flag], 72, FuForm.GACA_OCR,
               FuFiler.main_contractor),
    "AO-V": (B.airport_operator, S.verbal, [T.gaca_airside_flag], 1, None,
             FuFiler.main_contractor),
    "AO-W": (B.airport_operator, S.written, [T.any_airside_flag, T.env_airside], 24,
             FuForm.AO_OCR, FuFiler.main_contractor),
    "NCEC-W": (B.ncec, S.written, [T.env_ncec], 24, FuForm.NCEC_EIR, FuFiler.main_contractor),
}  # fmt: skip
CLIENT_TRIGGERS = [T.fatality, T.lti, T.any_do, T.hipo]
CLIENT: dict[str, tuple[S, int | None, FuForm | None]] = {
    "CL-V": (S.verbal, 1, None),
    "CL-F": (S.written, 24, FuForm.CLIENT_FLASH),
    "CL-I": (S.interim, 72, FuForm.CLIENT_INTERIM),
    "CL-FIN": (S.final, None, FuForm.CLIENT_FINAL),
}
PER_CASE_RULES = frozenset({"GOSI-W", "MHRSD-F"})  # NR-2 / NR-6

# form → (languages, field set)
FORMS: dict[FuForm, tuple[list[str], str]] = {
    FuForm.GOSI_WIR: (["ar"], "identity_medical"),
    FuForm.MHRSD_LTR: (["ar"], "identity"),
    FuForm.CD_LTR: (["ar"], "none"),
    FuForm.GACA_OCR: (["en", "ar"], "none"),
    FuForm.AO_OCR: (["en", "ar"], "none"),
    FuForm.NCEC_EIR: (["ar"], "none"),
    FuForm.CLIENT_FLASH: (["en", "ar"], "none"),
    FuForm.CLIENT_INTERIM: (["en", "ar"], "none"),
    FuForm.CLIENT_FINAL: (["en", "ar"], "none"),
}


def ensure_profile(db: Session, project_id: uuid.UUID) -> list[FuRule]:
    """The project's rules; the §3.11 default profile is created on first use. Client rows are
    active only when the project has client recipients (NR-9)."""
    rows = list(
        db.scalars(select(FuRule).where(FuRule.project_id == project_id).order_by(FuRule.rule_code))
    )
    if rows:
        return rows
    s = db.get(FuSettings, project_id)
    has_recipients = bool(s and s.client_recipients)
    for code, (body, stage, trig, hours, form, filer) in STATUTORY.items():
        db.add(
            FuRule(
                project_id=project_id, rule_code=code, body=body, stage=stage,
                source=FuRuleSource.statutory, triggers=[t.value for t in trig],
                trigger_params={}, deadline_hours=hours, deadline_basis=FuDeadlineBasis.trigger,
                form_code=form.value if form else None, filer=filer, active=True,
            )
        )  # fmt: skip
    for code, (stage, hours, form) in CLIENT.items():
        db.add(
            FuRule(
                project_id=project_id, rule_code=code, body=B.client, stage=stage,
                source=FuRuleSource.client, triggers=[t.value for t in CLIENT_TRIGGERS],
                trigger_params={}, deadline_hours=hours,
                deadline_basis=(FuDeadlineBasis.investigation_due if stage == S.final
                                else FuDeadlineBasis.trigger),
                form_code=form.value if form else None, filer=FuFiler.main_contractor,
                active=has_recipients,
            )
        )  # fmt: skip
    db.flush()
    return list(
        db.scalars(select(FuRule).where(FuRule.project_id == project_id).order_by(FuRule.rule_code))
    )


# ---- files ---------------------------------------------------------------------------------------

MAX_FILE = 5 * 1024 * 1024
TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".eml": "message/rfc822",
    ".txt": "text/plain",
    ".html": "text/html",
}


def store_file(
    db: Session,
    f: Any,
    owner: AttachmentOwner,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    fld: str,
) -> uuid.UUID:
    """Store an inline file (`FuFileInput`)."""
    from app.services import attachments  # noqa: PLC0415

    try:
        content = base64.b64decode(f.content_base64, validate=True)
    except ValueError as e:
        raise validation_error(fld, "The file is not valid base64.") from e
    if not content or len(content) > MAX_FILE:
        raise validation_error(fld, "Files must be between 1 byte and 5 MB.")
    ext = "." + f.file_name.rsplit(".", 1)[-1].lower() if "." in f.file_name else ""
    ctype = f.content_type or TYPES.get(ext)
    if ctype not in TYPES.values():
        raise validation_error(fld, "Use PDF, PNG, JPEG, EML or TXT.")
    a = attachments.store(
        db, owner, owner_id, project_id, f.file_name, content, str(ctype), user_id
    )
    return a.id


def store_bytes(
    db: Session,
    owner: AttachmentOwner,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    name: str,
    content: bytes,
    ctype: str,
    user_id: uuid.UUID,
) -> uuid.UUID:
    from app.services import attachments  # noqa: PLC0415

    return attachments.store(db, owner, owner_id, project_id, name, content, ctype, user_id).id


# ---- text: Arabic normalisation (LL-5), identity check (P6f-3), redaction (PK-3) -----------------

_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_TOKEN = re.compile(r"[\w]+", re.UNICODE)


def normalise(text: str | None) -> str:
    """LL-5: lower case, diacritics and tatweel removed; أ إ آ → ا; ة → ه; ى → ي; a leading ال
    of each word ignored; English plural 's' kept as typed."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    t = _DIACRITICS.sub("", t)
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    words = []
    for w in _TOKEN.findall(t):
        if w.startswith("ال") and len(w) > 3:
            w = w[2:]  # noqa: PLW2901
        words.append(w)
    return " ".join(words)


def search_terms(q: str) -> list[str]:
    return [w for w in normalise(q).split() if w]


def name_tokens(db: Session, incident_id: uuid.UUID | None) -> tuple[set[str], set[str]]:
    """P6f-3: the source incident's case person_name tokens (≥ 3 characters, normalised) and
    id_numbers."""
    from app.core import crypto  # noqa: PLC0415

    if incident_id is None:
        return set(), set()
    toks: set[str] = set()
    ids: set[str] = set()
    for c in db.scalars(select(InjuryCase).where(InjuryCase.incident_id == incident_id)):
        if c.anonymised_at is None:
            for w in normalise(re.sub(r"\(.*?\)", " ", c.person_name or "")).split():
                if len(w) >= 3:
                    toks.add(w)
        if c.id_number_enc:
            try:
                ids.add(crypto.decrypt(c.id_number_enc))
            except Exception:  # noqa: S112
                continue
    return toks, ids


def identity_hits(db: Session, incident_id: uuid.UUID | None, texts: dict[str, str | None]) -> str:
    """Name of the first field whose text holds a name token or an ID number, else ''."""
    toks, ids = name_tokens(db, incident_id)
    if not toks and not ids:
        return ""
    for fld, text in texts.items():
        if not text:
            continue
        words = set(normalise(text).split())
        if words & toks or any(i and i in text for i in ids):
            return fld
    return ""


def check_identity(
    db: Session, incident_id: uuid.UUID | None, texts: dict[str, str | None]
) -> None:
    fld = identity_hits(db, incident_id, texts)
    if fld:
        raise code_err(
            ErrorCode.IDENTITY_IN_TEXT,
            "The text names the injured person or holds an ID number (P6f-3): remove it.",
            "يحتوي النص على اسم المصاب أو رقم هوية: احذفه.",
            fld,
        )


def p18_warnings(texts: dict[str, str | None]) -> list[Any]:
    from app.schemas.hse_common import ApiWarning  # noqa: PLC0415
    from app.services.hse_common import POSSIBLE_ID  # noqa: PLC0415

    return [
        ApiWarning(code="POSSIBLE_ID_NUMBER", field=k,
                   message="The text may contain an ID number (P1-8): remove it.",
                   message_ar="قد يحتوي النص على رقم هوية: احذفه.")
        for k, v in texts.items() if v and POSSIBLE_ID.search(v)
    ]  # fmt: skip


def redact(db: Session, inc: Incident, text: str | None) -> str | None:
    """PK-3 / LL-2: injured names and ID numbers removed server-side (as T5)."""
    from app.ai.masking import redact as ai_redact  # noqa: PLC0415

    names = [
        c.person_name
        for c in db.scalars(select(InjuryCase).where(InjuryCase.incident_id == inc.id))
        if c.person_name
    ]
    return ai_redact(text, names)


# ---- Umm al-Qura date (PK-4) ---------------------------------------------------------------------

HIJRI_MONTHS_AR = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]  # fmt: skip


def hijri(d: date) -> tuple[int, int, int]:
    """Tabular (civil) Islamic calendar, an approximation of Umm al-Qura that may differ by one
    day (DECISIONS: VERIFY against the official calendar before printing letters)."""
    jd = d.toordinal() + 1721424.5
    jd = int(jd + 0.5)
    l_ = jd - 1948440 + 10632
    n = (l_ - 1) // 10631
    l_ = l_ - 10631 * n + 354
    j = ((10985 - l_) // 5316) * ((50 * l_) // 17719) + (l_ // 5670) * ((43 * l_) // 15238)
    l_ = l_ - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    m = (24 * l_) // 709
    day = l_ - (709 * m) // 24
    y = 30 * n + j - 30
    return y, m, day


def hijri_str(d: date) -> str:
    y, m, day = hijri(d)
    return f"{day} {HIJRI_MONTHS_AR[m - 1]} {y} هـ"


def end_of_day(d: date) -> datetime:
    from app.services.access import common as acommon  # noqa: PLC0415

    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=acommon.RIYADH)


def day_after(d: date) -> date:
    return d + timedelta(days=1)
