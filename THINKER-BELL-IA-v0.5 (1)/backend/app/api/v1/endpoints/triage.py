from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from backend.app.api.v1.endpoints.auth import require_roles
from backend.app.db.models import AccessLog, Patient, TriageEvaluation, User
from backend.app.db.session import get_db
from backend.app.schemas.out import (AccessLogPage, DashboardOut, EvaluationOut, EvaluationPage, News2InfoOut, VerifyOut)
from backend.app.schemas.triage import EvaluateIn
from backend.app.services.audit import append_access, append_audit, client_ip, eval_digest, verify_access_chain, verify_chain
from backend.app.services.timeutil import as_utc, day_end_utc, day_start_utc, local_day
from clinical.age import age_on, today_bogota
from clinical.algorithms.news2.calculator import ALGORITHM_VERSION, RULES_SOURCE, RULES_STATUS, NEWS2Calculator, VitalSigns
from clinical.special_populations import ALERTS_VERSION, PEDIATRIC_ROUTE, build_alerts

router = APIRouter(tags=["Clinical"])
ANY = ("admin", "clinician", "auditor")

def ser(x: TriageEvaluation):
    return {"evaluation_id": x.id, "timestamp": as_utc(x.timestamp), "patient_id": x.patient_id, "clinician_id": x.clinician_id,
            "total_score": x.total_score, "parameter_scores": x.parameter_scores, "vitals": x.vitals,
            "clinical_risk": x.clinical_risk, "recommended_response": x.recommended_response,
            "algorithm_version": x.algorithm_version, "rules_status": x.rules_status,
            "context": x.context, "alerts": (x.context or {}).get("alerts", [])}

@router.get("/news2/info", response_model=News2InfoOut)
def news2_info(user: User = Depends(require_roles(*ANY))):
    return {"algorithm_version": ALGORITHM_VERSION, "rules_status": RULES_STATUS, "source": RULES_SOURCE,
            "notice": "Módulo pendiente de validación clínica. No es diagnóstico ni dispositivo médico autorizado."}

@router.post("/triage/evaluate", status_code=201, response_model=EvaluationOut)
def evaluate(body: EvaluateIn, user: User = Depends(require_roles("clinician")), db: Session = Depends(get_db)):
    patient = db.get(Patient, body.patient_id)
    if not patient: raise HTTPException(404, "Paciente no encontrado; regístralo primero.")
    # Edad exacta si hay birth_date; si no, la registrada. La edad solo crece, así que la estática solo puede sobre-bloquear.
    if patient.birth_date: age, basis = age_on(patient.birth_date, today_bogota()), "birth_date"
    else: age, basis = patient.age, "recorded_static"
    if age < 16:  # RCP 2017, rec. 2: NEWS2 no debe usarse en menores de 16 años
        append_audit(db, event_type="triage_blocked_age", actor_id=user.id, patient_id=patient.id,
                     summary={"rule": "RCP2017-rec2", "age_basis": basis, "protocol_required": PEDIATRIC_ROUTE})
        db.commit()   # el bloqueo queda registrado aunque la petición falle
        raise HTTPException(422, {"code": "NEWS2_NOT_APPLICABLE", "protocol_required": PEDIATRIC_ROUTE,
                                  "message": "NEWS2 no está indicado para menores de 16 años (RCP 2017). Usa el protocolo pediátrico institucional."})
    alerts = build_alerts(body.pregnancy, body.spinal_cord_injury)
    context = {"pregnancy": body.pregnancy, "spinal_cord_injury": body.spinal_cord_injury, "age_basis": basis,
               "alerts_version": ALERTS_VERSION, "alerts": alerts}
    r = NEWS2Calculator.evaluate(VitalSigns(**body.vitals.model_dump()))
    ev = TriageEvaluation(patient_id=body.patient_id, clinician_id=user.id, total_score=r.total_score,
                          parameter_scores=r.parameter_scores, vitals=body.vitals.model_dump(mode="json"),
                          clinical_risk=r.clinical_risk, recommended_response=r.recommended_response,
                          algorithm_version=r.algorithm_version, rules_status=r.rules_status, context=context)
    try:
        db.add(ev); db.flush()
        append_audit(db, event_type="triage_evaluated", actor_id=user.id, patient_id=body.patient_id, evaluation_id=ev.id,
                     summary={"score": r.total_score, "algorithm_version": r.algorithm_version,
                              "alert_codes": [a["code"] for a in alerts], "eval_digest": eval_digest(ev)})
        db.commit()
    except Exception as exc:
        db.rollback(); raise HTTPException(500, "No fue posible guardar la evaluación.") from exc
    return ser(ev)

@router.get("/triage/evaluations", response_model=EvaluationPage)
def list_evaluations(request: Request, patient_id: str | None = Query(None, max_length=64),
                     risk: Literal["Bajo", "Bajo-Medio", "Medio", "Alto"] | None = None,
                     date_from: date | None = None, date_to: date | None = None, limit: int = Query(20, ge=1, le=100),
                     offset: int = Query(0, ge=0, le=100_000), user: User = Depends(require_roles(*ANY)), db: Session = Depends(get_db)):
    stmt = select(TriageEvaluation)
    if patient_id: stmt = stmt.where(TriageEvaluation.patient_id == patient_id)
    if risk: stmt = stmt.where(TriageEvaluation.clinical_risk == risk)
    if date_from: stmt = stmt.where(TriageEvaluation.timestamp >= day_start_utc(date_from))
    if date_to: stmt = stmt.where(TriageEvaluation.timestamp < day_end_utc(date_to))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(TriageEvaluation.timestamp.desc()).limit(limit).offset(offset)).scalars().all()
    append_access(db, actor_id=user.id, actor_role=user.role, action="list_evaluations", outcome="ok", ip=client_ip(request),
                  patient_id=patient_id, detail={"filters": {"risk": risk, "date_from": str(date_from) if date_from else None,
                  "date_to": str(date_to) if date_to else None}, "total": total, "ids": sorted({x.patient_id for x in rows})})
    db.commit()   # fail-closed
    return {"items": [ser(x) for x in rows], "total": total, "limit": limit, "offset": offset}

@router.get("/triage/evaluations/{evaluation_id}", response_model=EvaluationOut)
def get_evaluation(evaluation_id: str, request: Request, user: User = Depends(require_roles(*ANY)), db: Session = Depends(get_db)):
    x = db.get(TriageEvaluation, evaluation_id)
    append_access(db, actor_id=user.id, actor_role=user.role, action="read_evaluation", outcome="ok" if x else "not_found",
                  ip=client_ip(request), patient_id=x.patient_id if x else None, detail={"evaluation_id": evaluation_id})
    db.commit()
    if not x: raise HTTPException(404, "Evaluación no encontrada.")
    return ser(x)

@router.get("/dashboard/summary", response_model=DashboardOut)
def dashboard(request: Request, user: User = Depends(require_roles(*ANY)), db: Session = Depends(get_db)):
    day = local_day(db, TriageEvaluation.timestamp)
    per_day = db.execute(select(day, func.count()).group_by(day).order_by(day.desc()).limit(7)).all()
    recent = db.execute(select(TriageEvaluation).order_by(TriageEvaluation.timestamp.desc()).limit(5)).scalars().all()
    out = {"evaluations": db.scalar(select(func.count(TriageEvaluation.id))), "patients": db.scalar(select(func.count(Patient.id))),
           "risk_distribution": {k: n for k, n in db.execute(select(TriageEvaluation.clinical_risk, func.count()).group_by(TriageEvaluation.clinical_risk)).all()},
           "per_day": [{"day": d.isoformat(), "count": n} for d, n in reversed(per_day)], "recent": [ser(x) for x in recent]}
    append_access(db, actor_id=user.id, actor_role=user.role, action="dashboard", outcome="ok", ip=client_ip(request),
                  detail={"ids": sorted({x.patient_id for x in recent})})
    db.commit()
    return out

@router.get("/audit/verify", response_model=VerifyOut)
def audit_verify(user: User = Depends(require_roles("admin", "auditor")), db: Session = Depends(get_db)):
    ok, bad = verify_chain(db)
    return {"valid": ok, "first_invalid_seq": bad}

@router.get("/audit/verify-access", response_model=VerifyOut)
def access_verify(user: User = Depends(require_roles("admin", "auditor")), db: Session = Depends(get_db)):
    ok, bad = verify_access_chain(db)
    return {"valid": ok, "first_invalid_seq": bad}

@router.get("/audit/access-logs", response_model=AccessLogPage)
def access_logs(request: Request, action: str | None = Query(None, max_length=40), patient_id: str | None = Query(None, max_length=64),
                limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=100_000),
                user: User = Depends(require_roles("auditor")), db: Session = Depends(get_db)):
    stmt = select(AccessLog, User.username).outerjoin(User, User.id == AccessLog.actor_id)
    if action: stmt = stmt.where(AccessLog.action == action)
    if patient_id: stmt = stmt.where(AccessLog.patient_id == patient_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(AccessLog.seq.desc()).limit(limit).offset(offset)).all()
    append_audit(db, event_type="access_logs_viewed", actor_id=user.id, summary={"action": action, "patient_id": patient_id, "ip": client_ip(request)})
    db.commit()                                   # quién revisa la bitácora también queda registrado
    return {"items": [{"seq": a.seq, "timestamp": as_utc(a.event_timestamp), "actor": name, "actor_role": a.actor_role, "action": a.action,
                       "outcome": a.outcome, "ip": a.ip, "patient_id": a.patient_id, "detail": a.detail} for a, name in rows],
            "total": total, "limit": limit, "offset": offset}
