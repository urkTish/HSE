"""Root-cause analysis of an NCR (spec 8-quality Q-NCR-09, -10): the method must be allowed for the
class by `rca_method_by_class` (a repeat NCR also refuses `simple`, Q-NCR-16) and complete:

* `simple` — a cause statement ≥ 30 characters;
* `five_why` — 3 to 7 "why" answers of ≥ 10 characters and a root-cause statement;
* `ishikawa` — causes in ≥ 2 of the 6M categories and ≥ 1 cause marked root;
* `eight_d` — D1 team (≥ 2 users), D2 problem statement (what, where, when, how many; is / is not),
  D3 containment (= Q-NCR-07), D4 root cause and escape point, D5 ≥ 1 corrective action,
  D6 implementation and validation dates, D7 prevention of recurrence, D8 closure note.

The root cause's 6M category becomes the NCR's `cause_category`."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.core.errors import ErrorCode
from app.core.quality.common import QCauseCategory, QNcrClass, QNcrStatus, QRcaMethod
from app.models.quality import QNcr, QNcrRca
from app.schemas.hse_common import ApiWarning
from app.services.common import invalid_transition
from app.services.hse_common import id_warnings
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import settings as qs
from app.services.quality.ncr import core

M = QRcaMethod
HUMAN_ERROR = re.compile(
    r"\b(operator|human|worker|labou?r)\s+(error|mistake|fault)\b|خطأ\s*(المشغل|بشري|العامل)",
    re.IGNORECASE,
)


def incomplete(why: str, why_ar: str) -> Any:
    return qc.err(
        422,
        ErrorCode.RCA_INCOMPLETE,
        f"The root-cause analysis is incomplete: {why}",
        f"تحليل السبب الجذري غير مكتمل: {why_ar}",
    )


def allowed_methods(db: Session, n: QNcr) -> list[str]:
    table = qs.value(db, n.project_id, "rca_method_by_class")
    methods = list(table.get((n.classification or QNcrClass.minor).value, []))
    if n.repeat_of_id is not None:
        methods = [m for m in methods if m != M.simple.value]
    return methods


def check_method(db: Session, n: QNcr, method: QRcaMethod) -> None:
    if method.value not in allowed_methods(db, n):
        cls = n.classification.value if n.classification else ""
        raise qc.err(
            422,
            ErrorCode.RCA_METHOD_NOT_ALLOWED,
            f"{method.value} is not allowed for a {cls}"
            f" NCR{' (repeat)' if n.repeat_of_id else ''}; allowed: "
            f"{', '.join(allowed_methods(db, n)) or 'none'}.",
            "طريقة التحليل غير مسموحة لهذا التصنيف.",
        )


def _txt(v: Any) -> str:
    return str(v or "").strip()


def validate(
    db: Session, n: QNcr, method: QRcaMethod, data: dict[str, Any], cause: QCauseCategory | None
) -> tuple[str, QCauseCategory]:
    """Completeness (RCA_INCOMPLETE). Returns (root cause statement, cause category)."""
    if method == M.simple:
        stmt = _txt(data.get("cause"))
        if len(stmt) < 30:
            raise incomplete(
                "the cause statement needs at least 30 characters",
                "يجب ألا يقل بيان السبب عن 30 حرفاً",
            )
        root = stmt
    elif method == M.five_why:
        whys = [_txt(w) for w in data.get("whys") or []]
        if not 3 <= len(whys) <= 7 or any(len(w) < 10 for w in whys):
            raise incomplete(
                "give 3 to 7 'why' answers of at least 10 characters",
                "أدخل من 3 إلى 7 إجابات لماذا لا تقل كل منها عن 10 أحرف",
            )
        root = _txt(data.get("root_cause"))
        if len(root) < 10:
            raise incomplete("state the root cause", "اذكر السبب الجذري")
    elif method == M.ishikawa:
        causes = data.get("causes") or []
        cats = {c.get("category") for c in causes if _txt(c.get("text"))}
        roots = [c for c in causes if c.get("root") and _txt(c.get("text"))]
        if len(cats) < 2 or not roots:
            raise incomplete(
                "give causes in at least two 6M categories and mark one as root",
                "أدخل أسباباً في فئتين على الأقل وحدد السبب الجذري",
            )
        root = _txt(roots[0].get("text"))
        cause = QCauseCategory(roots[0]["category"])
    else:
        team = [x for x in data.get("d1_team") or [] if x]
        if len(set(map(str, team))) < 2:
            raise incomplete(
                "D1 needs a team of at least two users", "يتطلب D1 فريقاً من شخصين على الأقل"
            )
        d2 = data.get("d2_problem") or {}
        if not all(_txt(d2.get(k)) for k in ("what", "where", "when", "how_many", "is_not")):
            raise incomplete(
                "D2 needs what, where, when, how many and is / is not",
                "يتطلب D2 ماذا وأين ومتى وكم وما هو وما ليس",
            )
        if not qc.text_of(n.containment_en, n.containment_ar) and not _txt(
            data.get("d3_containment")
        ):
            raise incomplete("D3 containment is missing", "الاحتواء D3 مفقود")
        root = _txt(data.get("d4_root_cause"))
        if len(root) < 10 or len(_txt(data.get("d4_escape_point"))) < 10:
            raise incomplete(
                "D4 needs the root cause and the escape point",
                "يتطلب D4 السبب الجذري ونقطة الإفلات",
            )
        if not core.live_cas(db, n):
            raise incomplete(
                "D5 needs at least one corrective action", "يتطلب D5 إجراءً تصحيحياً واحداً على الأقل"
            )
        if not data.get("d6_implemented_on") or not data.get("d6_validated_on"):
            raise incomplete(
                "D6 needs the implementation and validation dates",
                "يتطلب D6 تاريخي التنفيذ والتحقق",
            )
        if len(_txt(data.get("d7_prevention"))) < 10 or len(_txt(data.get("d8_closure"))) < 10:
            raise incomplete(
                "D7 prevention and D8 closure note are required",
                "يلزم D7 منع التكرار وملاحظة الإغلاق D8",
            )
    if cause is None:
        raise incomplete("choose the 6M category of the root cause", "اختر فئة السبب الجذري")
    return root, cause


def warnings_for(method: QRcaMethod, data: dict[str, Any], root: str | None) -> list[ApiWarning]:
    out: list[ApiWarning] = []
    texts = [
        *(data.get("whys") or []),
        root or "",
        _txt(data.get("cause")),
        _txt(data.get("d4_root_cause")),
    ]
    texts += [_txt(c.get("text")) for c in data.get("causes") or []]
    if any(HUMAN_ERROR.search(str(t)) for t in texts):
        out.append(
            qc.warning(
                ErrorCode.HUMAN_ERROR_NOT_ROOT_CAUSE,
                '"Operator error" is not a root cause: ask why the error was possible (Q-NCR-10).',
                '"خطأ المشغل" ليس سبباً جذرياً: اسأل لماذا كان الخطأ ممكناً.',
                "data",
            )
        )
    joined = " ".join(str(t) for t in texts if t)
    out += id_warnings(rca=joined)
    return out


def save(
    db: Session, p: Principal, ncr_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QNcr, list[ApiWarning]]:
    n = core.get_ncr(db, p, ncr_id)
    qc.writable(core.project_of(db, n), p)
    if n.status != QNcrStatus.open:
        raise invalid_transition("NCR", n.status, "root-cause analysis")
    core._manager_grant(p, n)
    method = M(body["method"])
    data = dict(body.get("data") or {})
    cause = QCauseCategory(body["cause_category"]) if body.get("cause_category") else None
    check_method(db, n, method)
    final = body.get("final", True)
    root: str | None = _txt(body.get("root_cause")) or None
    if final:
        root, cause = validate(db, n, method, data, cause)
    r = core.rca_of(db, n)
    if r is None:
        r = QNcrRca(ncr_id=n.id, method=method, created_by_user_id=p.user.id)
        db.add(r)
    r.method = method
    r.data = data
    r.root_cause = root
    r.cause_category = cause
    r.complete = bool(final)
    r.updated_by_user_id = p.user.id
    n.cause_category = cause if final else n.cause_category
    db.flush()
    core._audit(
        db,
        p,
        n,
        AuditAction.update,
        after={"rca": method.value, "complete": r.complete, "cause": cause},
    )
    return n, warnings_for(method, data, root)


def check_for_propose(db: Session, n: QNcr, r: QNcrRca | None) -> None:
    if r is None or not r.complete:
        raise incomplete(
            "record and complete the root-cause analysis", "سجّل تحليل السبب الجذري وأكمله"
        )
    check_method(db, n, r.method)
    validate(db, n, r.method, r.data or {}, r.cause_category)
    if n.cause_category is None:
        n.cause_category = r.cause_category
