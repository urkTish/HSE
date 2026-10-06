"""AI-15 prompt masking and AI-5 redaction of free text sent to the model."""

import re
from collections.abc import Iterable

from app.core.hse_enums import AiPromptWarning

ID_RE = re.compile(r"(?<!\d)[12]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MOBILE_RE = re.compile(r"(?:\+|00)966[\s-]?5\d(?:[\s-]?\d){7}|(?<!\d)05\d(?:[\s-]?\d){7}(?!\d)")

ID_MASK = "[ID]"
EMAIL_MASK = "[EMAIL]"
MOBILE_MASK = "[MOBILE]"
NAME_MASK = "[NAME]"


def mask_prompt(text: str) -> tuple[str, list[AiPromptWarning]]:
    warnings: list[AiPromptWarning] = []
    out, n = MOBILE_RE.subn(MOBILE_MASK, text)
    if n:
        warnings.append(AiPromptWarning.MOBILE_MASKED)
    out, n = EMAIL_RE.subn(EMAIL_MASK, out)
    if n:
        warnings.append(AiPromptWarning.EMAIL_MASKED)
    out, n = ID_RE.subn(ID_MASK, out)
    if n:
        warnings.append(AiPromptWarning.ID_NUMBER_MASKED)
    return out, warnings


def redact(text: str | None, names: Iterable[str] = ()) -> str | None:
    """Removes IDs, contacts and the given person names (whole names and their parts of ≥ 3
    letters) from free text before it reaches the model."""
    if text is None:
        return None
    out = MOBILE_RE.sub(MOBILE_MASK, text)
    out = EMAIL_RE.sub(EMAIL_MASK, out)
    out = ID_RE.sub(ID_MASK, out)
    parts: set[str] = set()
    for name in names:
        clean = re.sub(r"\(.*?\)", " ", name or "").strip()
        if clean:
            parts.add(clean)
            parts.update(p for p in re.split(r"\s+", clean) if len(p) >= 3)
    for p in sorted(parts, key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(p)}(?!\w)", NAME_MASK, out, flags=re.IGNORECASE)
    return re.sub(rf"(?:{re.escape(NAME_MASK)}\s*)+", NAME_MASK + " ", out).strip()
