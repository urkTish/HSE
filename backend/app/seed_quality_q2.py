"""Demo seed of package Q2 materials, testing and lab, welding, calibration, competence (Part C)
(spec 8-quality Appendix A). `seed` runs after the Q0 seed; `seed_after_parts` runs from the
registry `SEEDS` after every part's seed (it builds the QX11 out-of-tolerance review from the
receiving usages Q3 may have recorded)."""

from sqlalchemy.orm import Session


def seed(db: Session) -> None:
    """Seed Q2's Appendix A records."""


def seed_after_parts(db: Session) -> None:
    """Records that need the other parts' seeds first."""
