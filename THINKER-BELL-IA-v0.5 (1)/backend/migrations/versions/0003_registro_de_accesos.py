"""registro de accesos (access_logs)

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "access_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("actor_role", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("patient_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
    )
    op.create_index(op.f("ix_access_logs_actor_id"), "access_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_access_logs_patient_id"), "access_logs", ["patient_id"], unique=False)

def downgrade() -> None:
    op.drop_index(op.f("ix_access_logs_patient_id"), table_name="access_logs")
    op.drop_index(op.f("ix_access_logs_actor_id"), table_name="access_logs")
    op.drop_table("access_logs")
