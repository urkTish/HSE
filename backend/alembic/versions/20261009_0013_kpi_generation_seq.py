"""kpi cache generation sequence

Cross-process invalidation of the per-process KPI facts cache: every committed fact write
advances the sequence and each cached read compares it (app.kpi.data).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09 20:30:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS kpi_generation_seq")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS kpi_generation_seq")
