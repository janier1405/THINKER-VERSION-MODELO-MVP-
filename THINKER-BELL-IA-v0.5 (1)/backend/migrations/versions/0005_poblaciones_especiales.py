"""fecha de nacimiento opcional y contexto clínico de la evaluación

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("patients", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("triage_evaluations", sa.Column("context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

def downgrade() -> None:
    op.drop_column("triage_evaluations", "context")
    op.drop_column("patients", "birth_date")
