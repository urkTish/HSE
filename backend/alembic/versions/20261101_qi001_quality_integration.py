"""Phase 8 Quality, integration: the columns the packages left to the integrator (D-370).

`q_customers.min_remaining_shelf_life_pct` (Q-RCV-01: product → customer → setting, D-353) and the
structured measurement of an M&TE usage on `q_mte_usage` (`value`, `limit_low`, `limit_high`,
`unit`; D-342), both on Q0 tables that wave-2 parts could not change. Sits on q4001.

Revision ID: qi001
Revises: q4001
Create Date: 2026-11-01 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'qi001'
down_revision: Union[str, Sequence[str], None] = 'q4001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'q_customers',
        sa.Column('min_remaining_shelf_life_pct', sa.Numeric(precision=6, scale=2), nullable=True),
    )
    op.add_column('q_mte_usage', sa.Column('value', sa.Numeric(precision=18, scale=6), nullable=True))
    op.add_column(
        'q_mte_usage', sa.Column('limit_low', sa.Numeric(precision=18, scale=6), nullable=True)
    )
    op.add_column(
        'q_mte_usage', sa.Column('limit_high', sa.Numeric(precision=18, scale=6), nullable=True)
    )
    op.add_column('q_mte_usage', sa.Column('unit', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('q_mte_usage', 'unit')
    op.drop_column('q_mte_usage', 'limit_high')
    op.drop_column('q_mte_usage', 'limit_low')
    op.drop_column('q_mte_usage', 'value')
    op.drop_column('q_customers', 'min_remaining_shelf_life_pct')
