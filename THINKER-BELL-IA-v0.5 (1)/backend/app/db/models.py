from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .session import Base

def utcnow(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # admin | clinician | auditor
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)  # subir invalida sesiones
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    lock_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)   # bloqueos consecutivos (backoff)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    evaluations: Mapped[list["TriageEvaluation"]] = relationship(back_populates="patient")

class TriageEvaluation(Base):
    __tablename__ = "triage_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True, nullable=False)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    parameter_scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    vitals: Mapped[dict] = mapped_column(JSON, nullable=False)
    clinical_risk: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    recommended_response: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(60), nullable=False)
    rules_status: Mapped[str] = mapped_column(String(50), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    patient: Mapped[Patient] = relationship(back_populates="evaluations")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    seq: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)  # el UNIQUE convierte una carrera en error, no en bifurcación
    evaluation_id: Mapped[str | None] = mapped_column(ForeignKey("triage_evaluations.id"), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)

class AccessLog(Base):
    __tablename__ = "access_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    seq: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)    # read_patient | list_patients | read_evaluation | list_evaluations | dashboard | break_glass_read_patient
    outcome: Mapped[str] = mapped_column(String(12), nullable=False)   # ok | not_found
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
