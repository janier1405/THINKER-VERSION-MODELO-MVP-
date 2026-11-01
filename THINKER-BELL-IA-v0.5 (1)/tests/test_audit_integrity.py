import hashlib, json, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from backend.app.db.models import AccessLog, AuditLog, TriageEvaluation, User
from backend.app.main import app
from backend.app.services import audit as A
from tests.conftest import CTX, login_as

P = {"patient_id": "SYN-001", "full_name": "Paciente Sintético", "age": 45, "gender": "unknown"}
V = {"respiratory_rate": 8, "oxygen_saturation": 97, "supplemental_oxygen": False, "spo2_scale_2": False,
     "systolic_bp": 120, "heart_rate": 78, "consciousness": "A", "temperature": 36.8}   # puntaje 3
pg_only = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requiere PostgreSQL (TEST_DATABASE_URL)")

def _flow(env):
    clin = login_as(env, "clin1")                                              # seq 1 = login_success
    assert clin.post("/api/v1/patients", json=P).status_code == 201
    r = clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-001", "vitals": V, **CTX}); assert r.status_code == 201
    return clin, r.json()

def _verify(env, path="audit"):
    return login_as(env, "aud1").get(f"/api/v1/audit/verify{'' if path == 'audit' else '-access'}").json()

def test_clean_flow_is_valid(env):
    _flow(env); assert _verify(env) == {"valid": True, "first_invalid_seq": None}

def test_timestamp_is_bound_to_hash(env):
    _flow(env); _, S = env
    with S() as s:
        s.execute(update(AuditLog).where(AuditLog.seq == 1).values(event_timestamp=datetime(2001, 1, 1, tzinfo=timezone.utc))); s.commit()
    assert _verify(env) == {"valid": False, "first_invalid_seq": 1}

@pytest.mark.parametrize("col,val", [("vitals", {**V, "heart_rate": 40}), ("clinical_risk", "Alto"), ("total_score", 0)])
def test_tampering_evaluation_is_detected(env, col, val):
    _flow(env); _, S = env
    with S() as s:
        seq = s.execute(select(AuditLog.seq).where(AuditLog.event_type == "triage_evaluated")).scalar_one()
        s.execute(update(TriageEvaluation).values(**{col: val})); s.commit()
    assert _verify(env) == {"valid": False, "first_invalid_seq": seq}

def test_evaluation_without_audit_event_is_detected(env):
    _flow(env); _, S = env
    with S() as s:
        uid = s.execute(select(User.id).where(User.username == "clin1")).scalar_one()
        s.add(TriageEvaluation(patient_id="SYN-001", clinician_id=uid, total_score=0, parameter_scores={}, vitals=V,
                               clinical_risk="Bajo", recommended_response="x", algorithm_version="x", rules_status="x")); s.commit()
    assert _verify(env)["valid"] is False

@pytest.mark.skipif(bool(os.getenv("TEST_DATABASE_URL")), reason="En PostgreSQL la FK impide el borrado")
def test_deleted_evaluation_is_detected(env):
    _flow(env); _, S = env
    with S() as s: s.execute(delete(TriageEvaluation)); s.commit()
    assert _verify(env)["valid"] is False

def test_unkeyed_recomputation_does_not_validate(env):
    _flow(env); _, S = env
    with S() as s:   # atacante con escritura en la BD pero sin AUDIT_KEY: reescribe la cadena con SHA-256 simple
        prev = None
        for r in s.execute(select(AuditLog).order_by(AuditLog.seq)).scalars():
            if r.seq == 1: r.summary = {"forjado": True}
            body = A._body(r.seq, r.event_timestamp, prev, A._row_fields(r, A._AUDIT_FIELDS))
            r.previous_hash = prev
            r.event_hash = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            prev = r.event_hash
        s.commit()
    assert _verify(env) == {"valid": False, "first_invalid_seq": 1}

def test_tail_truncation_needs_external_anchor(env):
    _flow(env); login_as(env, "aud1"); _, S = env       # el último evento es un login, no una evaluación
    with S() as s:
        anchor = A.make_anchor(s, "audit")
        s.execute(delete(AuditLog).where(AuditLog.seq == anchor["seq"])); s.commit()
    with S() as s:
        assert A.verify_chain(s) == (True, None)                     # límite conocido: sin ancla no se ve
        assert A.verify_chain(s, anchor) == (False, anchor["seq"])   # con ancla externa, sí

def test_reads_are_logged_and_chain_verifies(env):
    clin, _ = _flow(env); _, S = env
    assert clin.get("/api/v1/patients/SYN-001").status_code == 200
    assert clin.get("/api/v1/patients/NOPE").status_code == 404
    clin.get("/api/v1/patients"); clin.get("/api/v1/triage/evaluations", params={"patient_id": "SYN-001"}); clin.get("/api/v1/dashboard/summary")
    with S() as s: rows = s.execute(select(AccessLog).order_by(AccessLog.seq)).scalars().all()
    assert [(r.action, r.outcome) for r in rows] == [("read_patient", "ok"), ("read_patient", "not_found"), ("list_patients", "ok"),
                                                     ("list_evaluations", "ok"), ("dashboard", "ok")]
    assert rows[0].patient_id == "SYN-001" and rows[0].actor_role == "clinician" and rows[0].ip
    assert rows[2].detail["ids"] == ["SYN-001"]
    assert _verify(env, "access") == {"valid": True, "first_invalid_seq": None}
    with S() as s: s.execute(update(AccessLog).where(AccessLog.seq == 1).values(patient_id="OTRO")); s.commit()
    assert _verify(env, "access") == {"valid": False, "first_invalid_seq": 1}

def test_read_fails_closed_when_access_log_fails(env, monkeypatch):
    clin, _ = _flow(env)
    def boom(*a, **k): raise RuntimeError("fallo simulado del registro")
    monkeypatch.setattr("backend.app.api.v1.endpoints.patients.append_access", boom)
    c = TestClient(app, raise_server_exceptions=False); c.cookies.update(clin.cookies)
    r = c.get("/api/v1/patients/SYN-001")
    assert r.status_code == 500 and "Sintético" not in r.text

def test_two_audit_events_in_one_transaction_do_not_collide(env):
    _, S = env
    with S() as s:
        uid = s.execute(select(User.id)).scalars().first()
        A.append_audit(s, event_type="a", actor_id=uid); A.append_audit(s, event_type="b", actor_id=uid); s.commit()
        assert A.verify_chain(s) == (True, None)

@pg_only
def test_both_chains_under_concurrency(env):
    _, S = env
    with S() as s: u = s.execute(select(User)).scalars().first(); uid, role = u.id, u.role
    def w(i: int):
        with S() as s: A.append_audit(s, event_type="carga", actor_id=uid, summary={"i": i}); s.commit()
        with S() as s: A.append_access(s, actor_id=uid, actor_role=role, action="read_patient", outcome="ok", ip=None, patient_id="X", detail={"i": i}); s.commit()
    with ThreadPoolExecutor(20) as ex: list(ex.map(w, range(40)))
    with S() as s:
        assert A.verify_chain(s) == (True, None) and A.verify_access_chain(s) == (True, None)
