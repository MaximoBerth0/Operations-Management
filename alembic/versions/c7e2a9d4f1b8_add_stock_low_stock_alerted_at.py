"""add inventory_stock.low_stock_alerted_at

Revision ID: c7e2a9d4f1b8
Revises: b1f4c2a7d3e9
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e2a9d4f1b8'
down_revision: Union[str, Sequence[str], None] = 'b1f4c2a7d3e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'inventory_stock',
        sa.Column('low_stock_alerted_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('inventory_stock', 'low_stock_alerted_at')
