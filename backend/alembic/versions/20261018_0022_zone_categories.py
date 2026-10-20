"""Zone categories the administrator manages: zones.category and reference tombstones (D-274).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-18 00:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('zones', sa.Column('category', sa.String(length=60), nullable=True))
    op.add_column('reference_items', sa.Column('retired', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reference_items', 'retired')
    op.drop_column('zones', 'category')
