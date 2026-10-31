"""Demo seed of package Q4 documents, audits, suppliers, KPIs, SPC, COPQ, AI, report packs (Part E)
(spec 8-quality Appendix A).

Stub created by Q0 (§3.3a); `app.seed_quality.seed_quality_data` calls `seed` after the Q0 seed
(registry `SEEDS`)."""

from sqlalchemy.orm import Session


def seed(db: Session) -> None:
    """Seed Q4's Appendix A records (empty until Q4 is built)."""
