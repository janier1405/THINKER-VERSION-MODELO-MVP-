"""triggers append-only en tablas de evidencia (solo PostgreSQL)

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union
from alembic import op
from backend.app.db.append_only import DROP_STATEMENTS, STATEMENTS

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"

def upgrade() -> None:
    if _pg():
        for s in STATEMENTS: op.execute(s)

def downgrade() -> None:
    if _pg():
        for s in DROP_STATEMENTS: op.execute(s)
