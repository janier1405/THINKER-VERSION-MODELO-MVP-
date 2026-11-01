from sqlalchemy import select, update
from backend.app.db.models import AuditLog, User
from tests.conftest import CTX, login_as, PW

P = {"patient_id": "SYN-001", "full_name": "Paciente Sintético", "age": 45, "gender": "unknown"}
V = {"respiratory_rate": 8, "oxygen_saturation": 97, "supplemental_oxygen": False, "spo2_scale_2": False,
     "systolic_bp": 120, "heart_rate": 78, "consciousness": "A", "temperature": 36.8}

def test_health_and_unauthenticated(env):
    c, _ = env
    assert c.get("/health").status_code == 200
    for m, u in (("get", "/api/v1/patients"), ("get", "/api/v1/dashboard/summary"), ("get", "/api/v1/triage/evaluations")):
        assert getattr(c, m)(u).status_code == 401
    assert c.post("/api/v1/triage/evaluate", json={"patient_id": "X", "vitals": V, **CTX}).status_code == 401

def test_login(env):
    c, S = env
    assert c.post("/api/v1/auth/login", json={"username": "clin1", "password": "mala"}).status_code == 401
    assert c.post("/api/v1/auth/login", json={"username": "nadie", "password": PW}).status_code == 401
    with S() as s: assert s.execute(select(User).where(User.username == "clin1")).scalar_one().password_hash.startswith("$argon2")

def test_roles(env):
    clin, aud, adm = login_as(env, "clin1"), login_as(env, "aud1"), login_as(env, "admin1")
    assert clin.post("/api/v1/auth/users", json={"username": "nuevo1", "password": PW, "role": "clinician"}).status_code == 403
    assert adm.post("/api/v1/auth/users", json={"username": "nuevo1", "password": PW, "role": "clinician"}).status_code == 201
    assert adm.post("/api/v1/auth/users", json={"username": "corta", "password": "123", "role": "admin"}).status_code == 422
    assert aud.post("/api/v1/patients", json=P).status_code == 403
    assert adm.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-001", "vitals": V, **CTX}).status_code == 403
    assert clin.get("/api/v1/audit/verify").status_code == 403 and aud.get("/api/v1/audit/verify").status_code == 200

def test_full_flow_and_audit(env):
    c, S = env
    clin, aud = login_as(env, "clin1"), login_as(env, "aud1")
    assert clin.get("/api/v1/dashboard/summary").json()["evaluations"] == 0
    assert clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-001", "vitals": V, **CTX}).status_code == 404
    assert clin.post("/api/v1/patients", json=P).status_code == 201
    assert clin.post("/api/v1/patients", json={**P, "full_name": "SOBRESCRITO"}).status_code == 409
    assert clin.get("/api/v1/patients/SYN-001").json()["full_name"] == "Paciente Sintético"
    r = clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-001", "vitals": V, **CTX}); assert r.status_code == 201
    b = r.json(); assert b["total_score"] == 3 and b["clinical_risk"] == "Bajo-Medio" and b["rules_status"] == "PENDIENTE_DE_VALIDACION_CLINICA"
    h = aud.get("/api/v1/triage/evaluations", params={"patient_id": "SYN-001", "risk": "Bajo-Medio"}).json()
    assert h["total"] == 1 and h["items"][0]["evaluation_id"] == b["evaluation_id"]
    assert aud.get("/api/v1/triage/evaluations", params={"date_from": "2999-01-01"}).json()["total"] == 0
    assert aud.get(f"/api/v1/triage/evaluations/{b['evaluation_id']}").status_code == 200
    d = aud.get("/api/v1/dashboard/summary").json(); assert d["evaluations"] == 1 and d["patients"] == 1 and d["risk_distribution"] == {"Bajo-Medio": 1}
    assert aud.get("/api/v1/audit/verify").json()["valid"] is True
    with S() as s:  # manipulación → la cadena debe detectarla
        s.execute(update(AuditLog).where(AuditLog.seq == 2).values(summary={"score": 0})); s.commit()
    assert aud.get("/api/v1/audit/verify").json() == {"valid": False, "first_invalid_seq": 2}

def test_validation_errors(env):
    clin = login_as(env, "clin1")
    assert clin.post("/api/v1/patients", json={**P, "patient_id": "a b/<x>"}).status_code == 422
    clin.post("/api/v1/patients", json=P)
    assert clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-001", "vitals": {**V, "respiratory_rate": 0}, **CTX}).status_code == 422
    assert clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-001", "vitals": {k: v for k, v in V.items() if k != "supplemental_oxygen"}, **CTX}).status_code == 422
