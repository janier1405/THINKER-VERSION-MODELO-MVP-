import hashlib, hmac, json
from datetime import datetime, timezone
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from backend.app.core.security import AUDIT_KEY
from backend.app.db.models import AccessLog, AuditLog, TriageEvaluation

# Orden de locks obligatorio: fila de users -> AUDIT_LOCK -> ACCESS_LOCK. Si un endpoint escribe en ambas cadenas, en ese orden.
AUDIT_LOCK, ACCESS_LOCK = 727001, 727002
_AUDIT_FIELDS = ("evaluation_id", "actor_id", "patient_id", "event_type", "summary")
_ACCESS_FIELDS = ("actor_id", "actor_role", "action", "outcome", "ip", "patient_id", "detail")

def _iso(dt: datetime) -> str:
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)   # SQLite devuelve datetimes naive
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")

def _mac(d: dict) -> str:
    raw = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hmac.new(AUDIT_KEY, raw, hashlib.sha256).hexdigest()

def _eq(a: object, b: object) -> bool:
    return hmac.compare_digest(str(a).encode(), str(b).encode())   # bytes: un str no ASCII lanzaría TypeError

def _body(seq: int, ts: datetime, prev: str | None, fields: dict) -> dict:
    return {"seq": seq, "ts": _iso(ts), "prev": prev, **fields}

def _row_fields(r, names: tuple[str, ...]) -> dict:
    return {n: getattr(r, n) for n in names}

def client_ip(request) -> str | None:
    return request.client.host if request.client else None   # tras proxy: uvicorn --proxy-headers --forwarded-allow-ips=<IP del proxy>

def keyed_digest(domain: str, value: str) -> str:
    """Huella con llave (HMAC): no se puede revertir con un diccionario sin AUDIT_KEY."""
    return _mac({"domain": domain, "value": value})[:32]

def eval_digest(ev: TriageEvaluation) -> str:
    """Huella de la evaluación clínica completa; viaja dentro del evento de auditoría."""
    return _mac({"id": ev.id, "patient_id": ev.patient_id, "clinician_id": ev.clinician_id, "ts": _iso(ev.timestamp),
                 "total_score": ev.total_score, "parameter_scores": ev.parameter_scores, "vitals": ev.vitals,
                 "clinical_risk": ev.clinical_risk, "algorithm_version": ev.algorithm_version, "rules_status": ev.rules_status,
                 "context": ev.context})

def _append(db: Session, model, lock: int, fields: dict):
    db.flush()   # ANTES del lock: mantiene el orden fila -> advisory y hace visibles los eventos pendientes de esta transacción
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock})   # válido bajo READ COMMITTED (ver chequeo al arranque)
    last = db.execute(select(model).order_by(model.seq.desc()).limit(1)).scalar_one_or_none()
    seq, prev = (last.seq + 1, last.event_hash) if last else (1, None)
    ts = datetime.now(timezone.utc)
    row = model(seq=seq, event_timestamp=ts, previous_hash=prev, event_hash=_mac(_body(seq, ts, prev, fields)), **fields)
    db.add(row)
    return row

def append_audit(db: Session, *, event_type: str, actor_id: str, patient_id: str | None = None,
                 evaluation_id: str | None = None, summary: dict | None = None) -> AuditLog:
    return _append(db, AuditLog, AUDIT_LOCK, {"evaluation_id": evaluation_id, "actor_id": actor_id, "patient_id": patient_id,
                                              "event_type": event_type, "summary": summary or {}})

def append_access(db: Session, *, actor_id: str, actor_role: str, action: str, outcome: str, ip: str | None,
                  patient_id: str | None = None, detail: dict | None = None) -> AccessLog:
    return _append(db, AccessLog, ACCESS_LOCK, {"actor_id": actor_id, "actor_role": actor_role, "action": action, "outcome": outcome,
                                                "ip": ip, "patient_id": patient_id, "detail": detail or {}})

def _verify(db: Session, model, names: tuple[str, ...], anchor: dict | None, with_evals: bool) -> tuple[bool, int | None]:
    q = select(model, TriageEvaluation).outerjoin(TriageEvaluation, model.evaluation_id == TriageEvaluation.id) if with_evals else select(model)
    prev, expected, evaluated, anchor_seen = None, 1, 0, anchor is None
    for row in db.execute(q.order_by(model.seq).execution_options(yield_per=1000)):
        r, ev = row[0], (row[1] if with_evals else None)
        ok = r.seq == expected and r.previous_hash == prev and _eq(r.event_hash, _mac(_body(r.seq, r.event_timestamp, prev, _row_fields(r, names))))
        if ok and with_evals and r.event_type == "triage_evaluated":
            evaluated += 1
            ok = ev is not None and _eq(r.summary.get("eval_digest", ""), eval_digest(ev))
        if not ok:
            return False, r.seq
        if anchor is not None and r.seq == anchor["seq"]:
            if not _eq(r.event_hash, anchor["event_hash"]):
                return False, r.seq
            anchor_seen = True
        prev, expected = r.event_hash, expected + 1
    if not anchor_seen:
        return False, anchor["seq"]   # cola truncada: falta el evento anclado
    if with_evals and evaluated != db.scalar(select(func.count(TriageEvaluation.id))):
        return False, expected        # hay evaluaciones sin evento de auditoría
    return True, None

def verify_chain(db: Session, anchor: dict | None = None) -> tuple[bool, int | None]:
    return _verify(db, AuditLog, _AUDIT_FIELDS, anchor, with_evals=True)

def verify_access_chain(db: Session, anchor: dict | None = None) -> tuple[bool, int | None]:
    return _verify(db, AccessLog, _ACCESS_FIELDS, anchor, with_evals=False)

def make_anchor(db: Session, chain: str = "audit") -> dict | None:
    model = {"audit": AuditLog, "access": AccessLog}[chain]
    last = db.execute(select(model).order_by(model.seq.desc()).limit(1)).scalar_one_or_none()
    return None if last is None else {"chain": chain, "seq": last.seq, "event_hash": last.event_hash,
                                      "ts": _iso(datetime.now(timezone.utc))}
