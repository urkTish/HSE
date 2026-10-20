"""One worker per platform user: partial unique index on workers.user_id.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-19 00:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0023'
down_revision: Union[str, Sequence[str], None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'uq_workers_user',
        'workers',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text('user_id IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_workers_user', table_name='workers')
