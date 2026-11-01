"""esquema inicial

Revision ID: 0001
Revises: 
Create Date: 2026-10-26 21:23:07.021903

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('patients',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('age', sa.Integer(), nullable=False),
    sa.Column('gender', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('triage_evaluations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('patient_id', sa.String(length=64), nullable=False),
    sa.Column('clinician_id', sa.String(length=36), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('total_score', sa.Integer(), nullable=False),
    sa.Column('parameter_scores', sa.JSON(), nullable=False),
    sa.Column('vitals', sa.JSON(), nullable=False),
    sa.Column('clinical_risk', sa.String(length=30), nullable=False),
    sa.Column('recommended_response', sa.Text(), nullable=False),
    sa.Column('algorithm_version', sa.String(length=60), nullable=False),
    sa.Column('rules_status', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['clinician_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_triage_evaluations_clinical_risk'), 'triage_evaluations', ['clinical_risk'], unique=False)
    op.create_index(op.f('ix_triage_evaluations_clinician_id'), 'triage_evaluations', ['clinician_id'], unique=False)
    op.create_index(op.f('ix_triage_evaluations_patient_id'), 'triage_evaluations', ['patient_id'], unique=False)
    op.create_index(op.f('ix_triage_evaluations_timestamp'), 'triage_evaluations', ['timestamp'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=36), nullable=True),
    sa.Column('actor_id', sa.String(length=36), nullable=False),
    sa.Column('patient_id', sa.String(length=64), nullable=True),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('event_timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('event_hash', sa.String(length=64), nullable=False),
    sa.Column('previous_hash', sa.String(length=64), nullable=True),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['evaluation_id'], ['triage_evaluations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('seq')
    )
    op.create_index(op.f('ix_audit_logs_evaluation_id'), 'audit_logs', ['evaluation_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_audit_logs_evaluation_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_triage_evaluations_timestamp'), table_name='triage_evaluations')
    op.drop_index(op.f('ix_triage_evaluations_patient_id'), table_name='triage_evaluations')
    op.drop_index(op.f('ix_triage_evaluations_clinician_id'), table_name='triage_evaluations')
    op.drop_index(op.f('ix_triage_evaluations_clinical_risk'), table_name='triage_evaluations')
    op.drop_table('triage_evaluations')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    op.drop_table('patients')
