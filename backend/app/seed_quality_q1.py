"""Demo seed of package Q1 construction: ITP, inspection requests, punch lists, handover dossier
(Part B) (spec 8-quality Appendix A).

Stub created by Q0 (§3.3a); `app.seed_quality.seed_quality_data` calls `seed` after the Q0 seed
(registry `SEEDS`)."""

from sqlalchemy.orm import Session


def seed(db: Session) -> None:
    """Seed Q1's Appendix A records (empty until Q1 is built)."""
