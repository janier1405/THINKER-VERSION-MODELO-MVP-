from tests.conftest import login_as
P = {"patient_id": "SYN-777", "full_name": "Nombre Sintético", "age": 61, "gender": "female"}

def test_auditor_sees_pseudonymised_patients(env):
    clin, aud = login_as(env, "clin1"), login_as(env, "aud1")
    clin.post("/api/v1/patients", json=P)
    a = aud.get("/api/v1/patients").json()["items"][0]; assert a["full_name"] is None and a["age"] is None and a["patient_id"] == "SYN-777"
    assert aud.get("/api/v1/patients/SYN-777").json()["full_name"] is None
    assert clin.get("/api/v1/patients/SYN-777").json()["full_name"] == "Nombre Sintético"

def test_search_by_id_only(env):
    clin = login_as(env, "clin1"); clin.post("/api/v1/patients", json=P)
    assert clin.get("/api/v1/patients", params={"q": "SYN-7"}).json()["total"] == 1
    assert clin.get("/api/v1/patients", params={"q": "Nombre"}).json()["total"] == 0   # el nombre no es buscable (no viaja en URLs)

def test_deactivate_user_cuts_session_and_login(env):
    adm, clin = login_as(env, "admin1"), login_as(env, "clin1")
    assert adm.post("/api/v1/auth/users/admin1/deactivate").status_code == 409          # no a sí mismo
    assert adm.post("/api/v1/auth/users/nadie/deactivate").status_code == 404
    assert clin.post("/api/v1/auth/users/aud1/deactivate").status_code == 403
    assert adm.post("/api/v1/auth/users/clin1/deactivate").status_code == 204
    assert clin.get("/api/v1/auth/me").status_code == 401                                # sesión vigente cortada
    from fastapi.testclient import TestClient; from backend.app.main import app; from tests.conftest import PW
    assert TestClient(app).post("/api/v1/auth/login", json={"username": "clin1", "password": PW}).status_code == 401
    assert login_as(env, "aud1").get("/api/v1/audit/verify").json()["valid"] is True
