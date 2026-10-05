"""Search normalisation (spec §5.7 rule 45)."""

import re

_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_TRANSLATE = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})
_SPACES = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """Lower-case, strip Arabic diacritics/tatweel and unify common letter variants."""
    if not text:
        return ""
    t = _TASHKEEL.sub("", text).replace(_TATWEEL, "")
    t = t.translate(_TRANSLATE).casefold()
    return _SPACES.sub(" ", t).strip()


def search_blob(*parts: str | None) -> str:
    return " | ".join(normalize(p) for p in parts if p)


def like_pattern(q: str) -> str:
    escaped = normalize(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
