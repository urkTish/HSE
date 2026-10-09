"""Answer evaluation and scoring (spec 6d-field-assurance §6.1, §6.2, EXE-2, FND-1, AUD-2).

Pure functions over template items (dicts as stored in ChecklistTemplate.items) and answers (the
AnswerInput fields as dicts); the services persist the results."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.field_enums import SCORED_TYPES, FindingSeverity, ItemType, OptionMapping

D = Decimal
ZERO = D(0)
SEV_RANK = {
    FindingSeverity.ofi: 0,
    FindingSeverity.observation: 1,
    FindingSeverity.minor: 2,
    FindingSeverity.minor_nc: 2,
    FindingSeverity.major: 3,
    FindingSeverity.major_nc: 3,
    FindingSeverity.critical: 4,
}


@dataclass
class Eval:
    item: dict[str, Any]
    answer: dict[str, Any] | None
    shown: bool
    applicable: bool = False
    compliant: bool | None = None
    weight: Decimal = ZERO
    earned: Decimal = ZERO
    rating: int | None = None

    @property
    def code(self) -> str:
        return str(self.item["item_code"])

    @property
    def scored(self) -> bool:
        return ItemType(self.item["item_type"]) in SCORED_TYPES

    @property
    def non_compliant(self) -> bool:
        return self.applicable and self.compliant is False

    @property
    def critical(self) -> bool:
        return bool(self.item.get("critical"))


@dataclass
class Score:
    evals: list[Eval] = field(default_factory=list)
    applicable_count: int = 0
    compliant_count: int = 0
    applicable_weight: Decimal = ZERO
    earned_weight: Decimal = ZERO
    critical_fails: int = 0

    @property
    def pct(self) -> Decimal | None:
        if not self.applicable_weight:
            return None
        return self.earned_weight / self.applicable_weight * 100


def _err(code: ErrorCode, en: str, ar: str, fld: str) -> ApiError:
    from app.core.errors import field_error  # noqa: PLC0415

    return ApiError(422, code, en, ar, errors=[field_error(fld, en, "value_error", ar)])


def evaluate(
    items: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    airside: bool,
    *,
    require_all: bool = True,
    audit: bool = False,
) -> Score:
    """§6.1 per answer, §6.2 totals; EXE-2 validation (every shown scored item answered, `na`
    only where allowed, a non-compliant answer needs a note ≥ 10 chars and the photo)."""
    by_code = {a["item_code"]: (i, a) for i, a in enumerate(answers)}
    known = {it["item_code"] for it in items}
    for code in by_code:
        if code not in known:
            raise validation_error("answers", f"{code} is not an item of this template.")
    sc = Score()
    for it in sorted(items, key=lambda x: (x.get("section_code", ""), x.get("order", 0))):
        code = it["item_code"]
        shown = airside or not it.get("airside_only")
        idx, ans = by_code.get(code, (None, None))
        ev = Eval(it, ans, shown)
        sc.evals.append(ev)
        if not shown:
            continue  # §6.1: airside_only items outside airside zones are not applicable
        t = ItemType(it["item_type"])
        fld = f"answers[{idx}]" if idx is not None else "answers"
        w = D(int(it.get("weight") or 1))
        if t not in SCORED_TYPES:
            continue
        val = (ans or {}).get("answer")
        num = (ans or {}).get("numeric_value")
        if ans is None or (val in (None, "") and num is None):
            if require_all:
                raise validation_error(fld, f"{code}: every shown item must be answered (EXE-2).")
            continue
        if val == "na":
            if not it.get("na_allowed"):
                raise _err(ErrorCode.NA_NOT_ALLOWED, f"{code} cannot be answered not applicable.",
                           "لا يسمح بإجابة لا ينطبق لهذا البند.", fld)  # fmt: skip
            continue
        if t == ItemType.yes_no:
            if val not in ("compliant", "non_compliant"):
                raise validation_error(fld, f"{code}: compliant, non_compliant or na.")
            ev.applicable, ev.compliant = True, val == "compliant"
            ev.weight, ev.earned = w, (w if ev.compliant else ZERO)
        elif t == ItemType.rating_0_3:
            if val not in ("0", "1", "2", "3"):
                raise validation_error(fld, f"{code}: a rating 0–3 or na.")
            r = int(val)
            ev.rating = r
            ev.applicable, ev.compliant = True, r >= 2
            ev.weight, ev.earned = w, w * r / 3
        elif t == ItemType.numeric:
            rule = it.get("numeric_rule") or {}
            v = D(str(num if num is not None else val))
            ok = D(str(rule.get("min"))) <= v <= D(str(rule.get("max")))
            ev.applicable, ev.compliant = True, ok
            ev.weight, ev.earned = w, (w if ok else ZERO)
        elif t == ItemType.single_select:
            opts = {o["code"]: o for o in it.get("options") or []}
            if val not in opts:
                raise validation_error(fld, f"{code}: choose one of the options.")
            m = OptionMapping(opts[val]["maps_to"])
            if m == OptionMapping.info:
                continue  # §6.1: an info option is not applicable
            ev.applicable, ev.compliant = True, m == OptionMapping.compliant
            ev.weight, ev.earned = w, (w if ev.compliant else ZERO)
        sc.applicable_count += 1
        sc.compliant_count += int(bool(ev.compliant))
        sc.applicable_weight += ev.weight
        sc.earned_weight += ev.earned
        needs_note = ev.compliant is False or (ev.rating is not None and ev.rating <= 1)
        if needs_note:
            note = ((ans or {}).get("note") or "").strip()
            if len(note) < 10:
                raise validation_error(
                    f"{fld}.note", f"{code}: a note of at least 10 characters is required."
                )
            if (
                ev.compliant is False
                and it.get("photo_required_on_fail")
                and not ((ans or {}).get("photos") or (ans or {}).get("photo_ids"))
            ):
                raise _err(ErrorCode.PHOTO_REQUIRED, f"{code}: a photo is required.",
                           "الصورة مطلوبة لهذا البند.", fld)  # fmt: skip
        if ev.compliant is False and ev.critical:
            sc.critical_fails += 1
    return sc


def finding_severity(ev: Eval, audit: bool) -> FindingSeverity | None:
    """FND-1 / AUD-2: the computed severity (grade) of a non-compliant answer."""
    if audit:
        if ev.rating is not None:
            if ev.rating >= 3:
                return None
            if ev.critical and ev.rating <= 1:
                return FindingSeverity.major_nc
            return {0: FindingSeverity.major_nc, 1: FindingSeverity.minor_nc}.get(
                ev.rating, FindingSeverity.observation
            )
        if not ev.non_compliant:
            return None
        return FindingSeverity.major_nc if ev.critical else FindingSeverity.minor_nc
    if not ev.non_compliant:
        return None
    if ev.critical:
        return FindingSeverity.critical
    sev = ev.item.get("default_severity") or "minor"
    return FindingSeverity(sev)


def raised(base: FindingSeverity, wanted: FindingSeverity | None, fld: str) -> FindingSeverity:
    """FND-1: a severity may be raised, never lowered."""
    if wanted is None or wanted == base:
        return base
    if SEV_RANK[wanted] < SEV_RANK[base]:
        raise _err(ErrorCode.SEVERITY_LOWERED, "A finding severity cannot be lowered (FND-1).",
                   "لا يمكن خفض درجة خطورة الملاحظة.", fld)  # fmt: skip
    return wanted


def section_scores(
    sections: list[dict[str, Any]], evals: list[Eval]
) -> list[tuple[dict[str, Any], Decimal, Decimal]]:
    out = []
    for s in sorted(sections, key=lambda x: x.get("order", 0)):
        aw = sum((e.weight for e in evals if e.item.get("section_code") == s["code"]), ZERO)
        ew = sum((e.earned for e in evals if e.item.get("section_code") == s["code"]), ZERO)
        out.append((s, aw, ew))
    return out


def q(v: Decimal, places: str = "0.001") -> Decimal:
    return v.quantize(D(places), rounding=ROUND_HALF_UP)
