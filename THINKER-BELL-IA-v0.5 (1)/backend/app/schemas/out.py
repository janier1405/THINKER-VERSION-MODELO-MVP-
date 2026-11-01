from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel

Risk = Literal["Bajo", "Bajo-Medio", "Medio", "Alto"]
Role = Literal["admin", "clinician", "auditor"]

class UserOut(BaseModel):
    username: str
    role: Role
    must_change_password: bool

class PatientOut(BaseModel):
    patient_id: str
    full_name: str | None
    age: int | None
    birth_date: date | None
    gender: str
    created_at: datetime

class PatientPage(BaseModel):
    items: list[PatientOut]
    total: int
    limit: int
    offset: int

class AlertOut(BaseModel):
    code: str
    severity: Literal["hard", "soft"]
    text: str

class EvaluationOut(BaseModel):
    evaluation_id: str
    timestamp: datetime
    patient_id: str
    clinician_id: str
    total_score: int
    parameter_scores: dict[str, int]
    vitals: dict[str, int | float | bool | str]
    clinical_risk: Risk
    recommended_response: str
    algorithm_version: str
    rules_status: str
    context: dict[str, Any]
    alerts: list[AlertOut]

class EvaluationPage(BaseModel):
    items: list[EvaluationOut]
    total: int
    limit: int
    offset: int

class DayCount(BaseModel):
    day: str
    count: int

class DashboardOut(BaseModel):
    evaluations: int
    patients: int
    risk_distribution: dict[str, int]
    per_day: list[DayCount]
    recent: list[EvaluationOut]

class News2InfoOut(BaseModel):
    algorithm_version: str
    rules_status: str
    source: str
    notice: str

class VerifyOut(BaseModel):
    valid: bool
    first_invalid_seq: int | None

class AccessLogItem(BaseModel):
    seq: int
    timestamp: datetime
    actor: str | None
    actor_role: str
    action: str
    outcome: str
    ip: str | None
    patient_id: str | None
    detail: dict[str, Any]

class AccessLogPage(BaseModel):
    items: list[AccessLogItem]
    total: int
    limit: int
    offset: int
