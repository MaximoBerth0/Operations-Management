from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Import all model modules so their tables register on Base.metadata.
# Required for Alembic autogenerate to detect the full schema.
# Imported after Base is defined to avoid circular imports.
from app.auth import model as _auth_model  # noqa: E402,F401
from app.users import model as _users_model  # noqa: E402,F401
from app.rbac.models import permission as _rbac_permission  # noqa: E402,F401
from app.rbac.models import role as _rbac_role  # noqa: E402,F401
from app.rbac.models import role_permission as _rbac_role_permission  # noqa: E402,F401
from app.rbac.models import user_role as _rbac_user_role  # noqa: E402,F401
from app.inventory.models import category as _inv_category  # noqa: E402,F401
from app.inventory.models import location as _inv_location  # noqa: E402,F401
from app.inventory.models import product as _inv_product  # noqa: E402,F401
from app.inventory.models import reservation as _inv_reservation  # noqa: E402,F401
from app.inventory.models import stock as _inv_stock  # noqa: E402,F401
from app.orders.models import order as _orders_order  # noqa: E402,F401

""" Alembic commands

# Create new migration (auto-detect changes)
alembic revision --autogenerate -m "Add posts table"

# Create empty migration (manual)
alembic revision -m "Add index"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>

# Show current version
alembic current

# Show migration history
alembic history

# Show pending migrations
alembic heads
"""
