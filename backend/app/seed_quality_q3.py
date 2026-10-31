"""Demo seed of package Q3 logistics: receiving, storage and cold chain, stock, recalls, transport
(Part D) (spec 8-quality Appendix A).

Stub created by Q0 (§3.3a); `app.seed_quality.seed_quality_data` calls `seed` after the Q0 seed
(registry `SEEDS`)."""

from sqlalchemy.orm import Session


def seed(db: Session) -> None:
    """Seed Q3's Appendix A records (empty until Q3 is built)."""
