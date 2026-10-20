"""Automatic daily returns: HSE settings for standard hours and rest days, absence and overtime
on workforce returns (D-268).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-18 00:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('project_hse_settings', sa.Column('auto_man_hours', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('project_hse_settings', sa.Column('standard_hours_per_person_day', sa.Integer(), server_default='10', nullable=False))
    op.add_column('project_hse_settings', sa.Column('rest_days', postgresql.ARRAY(sa.String(length=40)), server_default="{friday}", nullable=False))
    op.add_column('workforce_returns', sa.Column('absent_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('workforce_returns', sa.Column('overtime_hours', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('workforce_returns', 'overtime_hours')
    op.drop_column('workforce_returns', 'absent_count')
    op.drop_column('project_hse_settings', 'rest_days')
    op.drop_column('project_hse_settings', 'standard_hours_per_person_day')
    op.drop_column('project_hse_settings', 'auto_man_hours')
