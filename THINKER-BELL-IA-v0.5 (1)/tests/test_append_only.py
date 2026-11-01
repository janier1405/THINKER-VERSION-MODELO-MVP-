import os
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from backend.app.db.append_only import STATEMENTS
from tests.conftest import CTX, login_as

pg_only = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requiere PostgreSQL (TEST_DATABASE_URL)")
P = {"patient_id": "SYN-001", "full_name": "Sintético", "age": 45, "gender": "unknown"}
V = {"respiratory_rate": 16, "oxygen_saturation": 97, "supplemental_oxygen": False, "spo2_scale_2": False,
     "systolic_bp": 120, "heart_rate": 78, "consciousness": "A", "temperature": 36.8}

@pg_only
def test_append_only_triggers_block_mutation_but_allow_inserts(env):
    _, S = env
    with S() as s:
        for stmt in STATEMENTS: s.execute(text(stmt))
        s.commit()
    clin = login_as(env, "clin1")                                          # INSERT en audit_logs: debe seguir funcionando
    assert clin.post("/api/v1/patients", json=P).status_code == 201
    assert clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-001", "vitals": V, **CTX}).status_code == 201
    assert clin.get("/api/v1/patients/SYN-001").status_code == 200         # INSERT en access_logs
    for sql in ("UPDATE audit_logs SET event_type='x'", "DELETE FROM audit_logs", "TRUNCATE audit_logs",
                "UPDATE access_logs SET action='x'", "DELETE FROM access_logs", "TRUNCATE access_logs",
                "UPDATE triage_evaluations SET total_score=0", "DELETE FROM triage_evaluations"):
        with S() as s:
            with pytest.raises(ProgrammingError, match="append-only"):
                s.execute(text(sql))
            s.rollback()
    assert login_as(env, "aud1").get("/api/v1/audit/verify").json()["valid"] is True   # los intentos no dejaron rastro
