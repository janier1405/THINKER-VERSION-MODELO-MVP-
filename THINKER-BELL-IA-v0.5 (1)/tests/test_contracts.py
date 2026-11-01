import dataclasses, os
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from backend.app.db.models import AuditLog, User
from backend.app.main import app
from backend.app.schemas.triage import VitalsIn
from clinical.algorithms.news2.calculator import VitalSigns
from tests.conftest import CTX, PW, login_as

P = {"patient_id": "SYN-1", "full_name": "Sintético", "age": 45, "gender": "unknown"}
V = {"respiratory_rate": 16, "oxygen_saturation": 97, "supplemental_oxygen": False, "spo2_scale_2": False,
     "systolic_bp": 120, "heart_rate": 78, "consciousness": "A", "temperature": 36.8}
pg_only = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requiere PostgreSQL (TEST_DATABASE_URL)")
LOGIN = "/api/v1/auth/login"

def test_schema_and_dataclass_fields_match():
    assert set(VitalsIn.model_fields) == {f.name for f in dataclasses.fields(VitalSigns)}

def test_valid_payload_and_int_temperature():
    assert VitalsIn.model_validate(V).temperature == 36.8
    assert VitalsIn.model_validate({**V, "temperature": 37}).temperature == 37.0

@pytest.mark.parametrize("bad", [
    {**{k: v for k, v in V.items() if k != "spo2_scale_2"}, "spo2_scale2": True},   # typo + falta el real
    {**V, "spo2_scale2": True},                                                     # campo desconocido
    {k: v for k, v in V.items() if k != "spo2_scale_2"},                            # falta campo requerido
    {**V, "respiratory_rate": "16"},                                                # str en int
    {**V, "respiratory_rate": True},                                                # bool en int
    {**V, "respiratory_rate": 16.0},                                                # float en int
    {**V, "supplemental_oxygen": 1},                                                # int en bool
    {**V, "temperature": "37.0"},                                                   # str en float
    {**V, "temperature": True},
    {**V, "oxygen_saturation": 101},
    {**V, "systolic_bp": 39},
])
def test_vitals_rejects_loose_input(bad):
    with pytest.raises(ValidationError):
        VitalsIn.model_validate(bad)

@pytest.mark.parametrize("t", ["NaN", "Infinity", "-Infinity"])
def test_vitals_rejects_nan_and_inf(t):
    raw = ('{"respiratory_rate":16,"oxygen_saturation":97,"supplemental_oxygen":false,"spo2_scale_2":false,'
           '"systolic_bp":120,"heart_rate":78,"consciousness":"A","temperature":%s}' % t)
    with pytest.raises(ValidationError):
        VitalsIn.model_validate_json(raw)

def test_api_rejects_typo_and_extra_fields(env):
    clin = login_as(env, "clin1")
    assert clin.post("/api/v1/patients", json=P).status_code == 201
    typo = {k: v for k, v in V.items() if k != "spo2_scale_2"} | {"spo2_scale2": True}
    assert clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-1", "vitals": typo, **CTX}).status_code == 422
    assert clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-1", "vitals": V, **CTX, "x": 1}).status_code == 422
    assert clin.post("/api/v1/patients", json={**P, "patient_id": "SYN-2", "extra": 1}).status_code == 422
    assert clin.get("/api/v1/triage/evaluations", params={"risk": "Inventado"}).status_code == 422
    assert clin.get("/api/v1/patients", params={"q": "x" * 65}).status_code == 422
    r = TestClient(app).post(LOGIN, json={"username": "clin1", "password": PW, "otro": 1})
    assert r.status_code == 422

@pg_only
def test_parallel_bruteforce_cannot_exceed_lockout(env):
    _, S = env
    def bad(_): return TestClient(app).post(LOGIN, json={"username": "clin1", "password": "mala"}).status_code
    with ThreadPoolExecutor(12) as ex: codes = list(ex.map(bad, range(12)))
    assert set(codes) == {401}
    with S() as s:
        events = [a.event_type for a in s.execute(select(AuditLog)).scalars()]
        assert events.count("login_failed") == 4 and events.count("account_locked") == 1   # exacto: 4 + bloqueo en el 5.º
        assert s.execute(select(User).where(User.username == "clin1")).scalar_one().locked_until is not None
    assert TestClient(app).post(LOGIN, json={"username": "clin1", "password": PW}).status_code == 401

@pg_only
def test_login_logout_deactivate_do_not_deadlock(env):
    adm = login_as(env, "admin1")
    def cycle(i: int) -> list[int]:
        c, out = TestClient(app), []
        for _ in range(3):
            pw = "mala" if i % 3 == 0 else PW
            out.append(c.post(LOGIN, json={"username": "aud1", "password": pw}).status_code)
            out.append(c.post("/api/v1/auth/logout").status_code)
        return out
    def deactivate() -> int: return adm.post("/api/v1/auth/users/aud1/deactivate").status_code
    with ThreadPoolExecutor(8) as ex:
        futs = [ex.submit(cycle, i) for i in range(6)] + [ex.submit(deactivate)]
        codes = []
        for f in futs:
            r = f.result(); codes.extend(r if isinstance(r, list) else [r])
    assert 500 not in codes                      # un deadlock (40P01) saldría como 500
    assert adm.post("/api/v1/auth/users/aud1/deactivate").status_code == 204
