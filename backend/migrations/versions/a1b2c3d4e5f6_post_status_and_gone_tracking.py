"""post status and gone tracking

Revision ID: a1b2c3d4e5f6
Revises: fdbeae364b12
Create Date: 2026-07-30 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fdbeae364b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'posts',
        sa.Column(
            'status',
            sa.Enum('active', 'gone', name='post_status'),
            nullable=False,
            server_default='active',
        ),
    )
    op.add_column('posts', sa.Column('gone_sim_hours', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('posts', 'gone_sim_hours')
    op.drop_column('posts', 'status')
