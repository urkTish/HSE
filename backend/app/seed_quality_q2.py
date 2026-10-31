"""Demo seed of package Q2 materials, testing and lab, welding, calibration, competence (Part C)
(spec 8-quality Appendix A).

Stub created by Q0 (§3.3a); `app.seed_quality.seed_quality_data` calls `seed` after the Q0 seed
(registry `SEEDS`)."""

from sqlalchemy.orm import Session


def seed(db: Session) -> None:
    """Seed Q2's Appendix A records (empty until Q2 is built)."""
