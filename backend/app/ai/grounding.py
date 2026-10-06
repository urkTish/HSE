"""AI-2 number-grounding check and the AI-8/AI-9/AI-11 language checks.

Every number in the answer must appear (at display precision) in the turn's tool outputs or in
the user's question. Exempt: markdown list markers, citation markers [S1], codes such as K-21,
E1, L3 and references such as INC-ANIA-EXP-2026-0147.
"""

import json
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
NUM_RE = re.compile(r"(?<![\w.\-/])[-−+]?\d[\d,]*(?:\.\d+)?(?![\w])")
LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
CITE_RE = re.compile(r"\[(?:S|R)\d+(?:\s*,\s*(?:S|R)\d+)*\]")
CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b|\b[A-Z]{1,3}\d+\b")
TREND_RE = re.compile(
    r"\b(?:upward|downward|increasing|decreasing|rising|falling|improving|worsening)\s+trend\b"
    r"|\btrending\s+(?:up|down|upwards|downwards)\b",
    re.IGNORECASE,
)
CAUSAL_RE = re.compile(r"\b(?:caused\s+by|causes|causing|because\s+of|led\s+to)\b", re.I)


def _norm(raw: str) -> Decimal | None:
    s = raw.replace(",", "").replace("−", "-").lstrip("+")
    try:
        return abs(Decimal(s))
    except InvalidOperation:
        return None


def numbers_in(text: str) -> list[tuple[str, Decimal]]:
    t = text.translate(ARABIC_DIGITS)
    t = CITE_RE.sub(" ", t)
    t = CODE_RE.sub(" ", t)
    t = LIST_MARKER_RE.sub(" ", t)
    out = []
    for m in NUM_RE.finditer(t):
        v = _norm(m.group())
        if v is not None:
            out.append((m.group(), v))
    return out


def _strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            yield from _strings(v)
    elif obj is not None and not isinstance(obj, bool):
        yield str(obj)


def allowed_numbers(tool_outputs: Iterable[Any], extra_texts: Iterable[str] = ()) -> set[Decimal]:
    allowed: set[Decimal] = set()
    texts = [*(s for o in tool_outputs for s in _strings(o)), *extra_texts]
    for s in texts:
        t = s.translate(ARABIC_DIGITS)
        for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", t):
            v = _norm(m.group())
            if v is not None:
                allowed.add(v)
        for part in re.findall(r"\d+", t):  # dates "2026-09-08", refs, ratios
            allowed.add(Decimal(int(part)))
    return allowed


def check(answer: str, tool_outputs: list[Any], question: str = "") -> list[str]:
    """Numbers in `answer` not found in the tool outputs (empty = grounded)."""
    allowed = allowed_numbers(tool_outputs, [question])
    failures: list[str] = []
    for raw, v in numbers_in(answer):
        if v not in allowed and raw not in failures:
            failures.append(raw)
    return failures


def language_issues(answer: str, tool_outputs: list[dict[str, Any]]) -> list[str]:
    """AI-8: trend wording only when a tool returned trend_established = true; AI-9: never
    causal wording, association wording only when a T9 result is sufficient and p < 0.05."""
    issues: list[str] = []
    blob = json.dumps(tool_outputs, default=str)
    if TREND_RE.search(answer) and '"trend_established": true' not in blob:
        issues.append("trend_not_established")
    if CAUSAL_RE.search(answer):
        issues.append("causal_language")
    assoc = re.search(r"\bassociated with\b", answer, re.I)
    if assoc and '"supports_association": true' not in blob:
        issues.append("association_not_supported")
    return issues
