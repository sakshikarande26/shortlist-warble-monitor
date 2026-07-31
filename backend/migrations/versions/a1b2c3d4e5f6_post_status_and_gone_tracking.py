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


# Named once and reused for both the column definition and the explicit
# create/drop calls below, so add_column and the CREATE TYPE both agree on
# the same Postgres enum type.
post_status_enum = sa.Enum('active', 'gone', name='post_status')


def upgrade() -> None:
    bind = op.get_bind()
    # op.add_column (unlike op.create_table) does not auto-emit CREATE TYPE
    # for an Enum column on Postgres — that only happens as part of table
    # creation — so it has to be created explicitly here first.
    # checkfirst=True makes this safe to re-run. On SQLite there's no native
    # enum type (it's just a CHECK constraint on the column), so .create()
    # is a no-op there — same code works on both.
    post_status_enum.create(bind, checkfirst=True)
    op.add_column(
        'posts',
        sa.Column(
            'status',
            post_status_enum,
            nullable=False,
            server_default='active',
        ),
    )
    op.add_column('posts', sa.Column('gone_sim_hours', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('posts', 'gone_sim_hours')
    op.drop_column('posts', 'status')
    # Symmetric to upgrade(): drop_column doesn't drop the Postgres type
    # either, so drop it explicitly. No-op on SQLite.
    post_status_enum.drop(op.get_bind(), checkfirst=True)
