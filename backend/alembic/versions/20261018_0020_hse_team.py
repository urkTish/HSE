"""HSE department hierarchy: position and reports-to on users (D-270).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-18 00:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, Sequence[str], None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('hse_position', sa.String(length=40), nullable=True))
    op.add_column('users', sa.Column('reports_to_user_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_users_reports_to_user_id_users'), 'users', 'users', ['reports_to_user_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('fk_users_reports_to_user_id_users'), 'users', type_='foreignkey')
    op.drop_column('users', 'reports_to_user_id')
    op.drop_column('users', 'hse_position')
