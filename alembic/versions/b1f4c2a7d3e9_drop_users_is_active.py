"""drop users.is_active

`is_active` is now a read-only property on the User model derived from
`disabled_at`, so the stale column has to go: it is NOT NULL with no
server default, and inserts no longer supply it.

Revision ID: b1f4c2a7d3e9
Revises: aed0661c104a
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1f4c2a7d3e9'
down_revision: Union[str, Sequence[str], None] = 'aed0661c104a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('users', 'is_active')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), nullable=True),
    )
    op.execute('UPDATE users SET is_active = (disabled_at IS NULL)')
    op.alter_column('users', 'is_active', nullable=False)
