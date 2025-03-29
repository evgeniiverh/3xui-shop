"""merge multiple heads

Revision ID: merge_heads
Revises: add_is_blocked_to_users, 579d48dd94ef
Create Date: 2024-03-29 07:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_heads_20240329'
down_revision = ('add_is_blocked_to_users', '579d48dd94ef')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a merge migration, no changes needed
    pass


def downgrade() -> None:
    # This is a merge migration, no changes needed
    pass 