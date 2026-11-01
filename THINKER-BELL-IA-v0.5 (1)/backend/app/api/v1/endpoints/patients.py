from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.api.v1.endpoints.auth import require_roles
from backend.app.db.models import Patient, User
from backend.app.db.session import get_db
from backend.app.schemas.out import PatientOut, PatientPage
from backend.app.schemas.triage import BreakGlassIn, PatientIn
from backend.app.services.audit import append_access, append_audit, client_ip
from backend.app.services.timeutil import as_utc

router = APIRouter(prefix="/patients", tags=["Patients"])
ANY = ("admin", "clinician", "auditor")
HIDE_PII = ("auditor", "admin")           # minimización: la PII la ven los clínicos o un acceso de emergencia registrado
BREAK_GLASS_ROLES = ("admin",)

def ser(p: Patient, role: str = "clinician", reveal: bool = False):
    hide = role in HIDE_PII and not reveal
    return {"patient_id": p.id, "full_name": None if hide else p.full_name, "age": None if hide else p.age,
            "birth_date": None if hide else p.birth_date, "gender": p.gender, "created_at": as_utc(p.created_at)}

@router.post("", status_code=201, response_model=PatientOut)
def create_patient(body: PatientIn, request: Request, user: User = Depends(require_roles("admin", "clinician")), db: Session = Depends(get_db)):
    if db.get(Patient, body.patient_id): raise HTTPException(409, "El paciente ya existe; no se sobrescribe.")
    p = Patient(id=body.patient_id, full_name=body.full_name, age=body.age, birth_date=body.birth_date, gender=body.gender)
    db.add(p)
    try:
        db.flush()
        append_audit(db, event_type="patient_created", actor_id=user.id, patient_id=p.id, summary={"ip": client_ip(request)})
        db.commit()
    except IntegrityError:   # carrera entre dos altas del mismo ID
        db.rollback(); raise HTTPException(409, "El paciente ya existe; no se sobrescribe.")
    return ser(p)

@router.get("", response_model=PatientPage)
def list_patients(request: Request, q: str | None = Query(None, max_length=64), limit: int = Query(20, ge=1, le=100),
                  offset: int = Query(0, ge=0, le=100_000), user: User = Depends(require_roles(*ANY)), db: Session = Depends(get_db)):
    stmt = select(Patient)
    if q: stmt = stmt.where(Patient.id.istartswith(q, autoescape=True))  # solo por ID: nombres en query string acabarían en logs de acceso
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Patient.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    append_access(db, actor_id=user.id, actor_role=user.role, action="list_patients", outcome="ok", ip=client_ip(request),
                  detail={"q": q, "total": total, "ids": [p.id for p in rows]})
    db.commit()   # fail-closed: si el registro falla, no se devuelve nada
    return {"items": [ser(p, user.role) for p in rows], "total": total, "limit": limit, "offset": offset}

@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, request: Request, user: User = Depends(require_roles(*ANY)), db: Session = Depends(get_db)):
    p = db.get(Patient, patient_id)
    append_access(db, actor_id=user.id, actor_role=user.role, action="read_patient", outcome="ok" if p else "not_found",
                  ip=client_ip(request), patient_id=patient_id)
    db.commit()
    if not p: raise HTTPException(404, "Paciente no encontrado.")
    return ser(p, user.role)

@router.post("/{patient_id}/break-glass", response_model=PatientOut)
def break_glass(patient_id: str, body: BreakGlassIn, request: Request,
                user: User = Depends(require_roles(*BREAK_GLASS_ROLES)), db: Session = Depends(get_db)):
    p = db.get(Patient, patient_id)
    append_access(db, actor_id=user.id, actor_role=user.role, action="break_glass_read_patient",
                  outcome="ok" if p else "not_found", ip=client_ip(request), patient_id=patient_id, detail={"reason": body.reason})
    db.commit()                                   # fail-closed: sin registro no hay dato
    if not p: raise HTTPException(404, "Paciente no encontrado.")
    return ser(p, user.role, reveal=True)
