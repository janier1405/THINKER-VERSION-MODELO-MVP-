import json, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from backend.app.api.v1.endpoints.auth import _lock_minutes
from backend.app.db.models import AccessLog, AuditLog, User
from backend.app.main import app
from tests.conftest import PW, login_as

NEW = "otra-contrasena-segura-456"
LOGIN, CHG = "/api/v1/auth/login", "/api/v1/auth/change-password"
P = {"patient_id": "SYN-1", "full_name": "Nombre Sintético", "birth_date": "1980-05-17", "gender": "unknown"}
pg_only = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requiere PostgreSQL (TEST_DATABASE_URL)")
aware = lambda d: d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def events(S, t=None):
    with S() as s: return [a.event_type for a in s.execute(select(AuditLog).order_by(AuditLog.seq)).scalars() if t in (None, a.event_type)]

def bad_logins(user="clin1", n=5):
    c = TestClient(app)
    return [c.post(LOGIN, json={"username": user, "password": "mala-contrasena-1"}).status_code for _ in range(n)]

# --- M-6: PII y break-glass ---
def test_admin_and_auditor_do_not_see_pii(env):
    clin, adm, aud = login_as(env, "clin1"), login_as(env, "admin1"), login_as(env, "aud1")
    assert clin.post("/api/v1/patients", json=P).status_code == 201
    for c in (adm, aud):
        r = c.get("/api/v1/patients/SYN-1").json()
        assert (r["full_name"], r["age"], r["birth_date"]) == (None, None, None) and r["patient_id"] == "SYN-1"
        assert c.get("/api/v1/patients").json()["items"][0]["full_name"] is None
    assert clin.get("/api/v1/patients/SYN-1").json()["full_name"] == "Nombre Sintético"

def test_break_glass_flow_and_review(env):
    clin, adm, aud = login_as(env, "clin1"), login_as(env, "admin1"), login_as(env, "aud1")
    clin.post("/api/v1/patients", json=P)
    url, ok = "/api/v1/patients/SYN-1/break-glass", {"reason": "Corrección de registro solicitada por soporte"}
    assert clin.post(url, json=ok).status_code == 403 and aud.post(url, json=ok).status_code == 403
    for bad in ({"reason": "corto"}, {"reason": " " * 20}, {}, {**ok, "x": 1}):
        assert adm.post(url, json=bad).status_code == 422
    r = adm.post(url, json=ok); assert r.status_code == 200 and r.json()["full_name"] == "Nombre Sintético"
    assert adm.post("/api/v1/patients/NOPE/break-glass", json=ok).status_code == 404
    with env[1]() as s:
        rows = s.execute(select(AccessLog).where(AccessLog.action == "break_glass_read_patient").order_by(AccessLog.seq)).scalars().all()
    assert [(x.outcome, x.actor_role) for x in rows] == [("ok", "admin"), ("not_found", "admin")] and rows[0].detail["reason"] == ok["reason"]
    assert login_as(env, "aud1").get("/api/v1/audit/verify-access").json()["valid"] is True
    got = aud.get("/api/v1/audit/access-logs", params={"action": "break_glass_read_patient"}).json()
    assert got["total"] == 2 and got["items"][1]["actor"] == "admin1"
    assert adm.get("/api/v1/audit/access-logs").status_code == 403 and clin.get("/api/v1/audit/access-logs").status_code == 403
    assert "access_logs_viewed" in events(env[1])

def test_break_glass_fails_closed(env, monkeypatch):
    clin, adm = login_as(env, "clin1"), login_as(env, "admin1")
    clin.post("/api/v1/patients", json=P)
    def boom(*a, **k): raise RuntimeError("fallo simulado")
    monkeypatch.setattr("backend.app.api.v1.endpoints.patients.append_access", boom)
    c = TestClient(app, raise_server_exceptions=False); c.cookies.update(adm.cookies); c.headers["X-CSRF-Token"] = adm.headers["X-CSRF-Token"]
    r = c.post("/api/v1/patients/SYN-1/break-glass", json={"reason": "Motivo suficientemente largo"})
    assert r.status_code == 500 and "Sintético" not in r.text

# --- M-7: cambio obligatorio ---
def test_new_user_must_change_password_before_anything_else(env):
    adm = login_as(env, "admin1")
    assert adm.post("/api/v1/auth/users", json={"username": "nuevo1", "password": PW, "role": "clinician"}).status_code == 201
    other, c = login_as(env, "nuevo1"), login_as(env, "nuevo1")
    r = c.get("/api/v1/patients"); assert r.status_code == 403 and r.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert c.get("/api/v1/auth/me").json()["must_change_password"] is True
    assert c.post(CHG, json={"current_password": "mala-contrasena-1", "new_password": NEW}).status_code == 403
    assert c.post(CHG, json={"current_password": PW, "new_password": PW}).status_code == 422             # igual a la actual
    assert c.post(CHG, json={"current_password": PW, "new_password": "xxx-nuevo1-yyyy"}).status_code == 422   # contiene el usuario
    assert c.post(CHG, json={"current_password": PW, "new_password": "corta"}).status_code == 422
    r = c.post(CHG, json={"current_password": PW, "new_password": NEW}); assert r.status_code == 200 and r.json()["must_change_password"] is False
    c.headers["X-CSRF-Token"] = c.cookies.get("tb_csrf")                      # la sesión recibe CSRF nuevo
    assert c.get("/api/v1/patients").status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401                    # las demás sesiones quedan cortadas
    assert TestClient(app).post(LOGIN, json={"username": "nuevo1", "password": PW}).status_code == 401
    assert TestClient(app).post(LOGIN, json={"username": "nuevo1", "password": NEW}).status_code == 200
    assert "password_changed" in events(env[1])

def test_cli_style_users_are_not_forced(env):
    assert login_as(env, "clin1").get("/api/v1/patients").status_code == 200   # fixture: must_change_password=False por defecto

def test_wrong_current_password_shares_the_lockout(env):
    cl = login_as(env, "clin1")
    assert [cl.post(CHG, json={"current_password": "incorrecta-123456", "new_password": NEW}).status_code for _ in range(5)] == [403] * 5
    assert "account_locked" in events(env[1]) and events(env[1], "password_change_failed")
    assert TestClient(app).post(LOGIN, json={"username": "clin1", "password": PW}).status_code == 401

# --- M-4: backoff y desbloqueo ---
def test_lock_minutes_curve_and_cap():
    assert [_lock_minutes(i) for i in range(8)] == [1, 2, 4, 8, 16, 30, 30, 30] and _lock_minutes(10**6) == 30

def test_lock_doubles_per_lock_and_resets_on_success(env):
    _, S = env
    def lock_minutes():
        with S() as s: u = s.execute(select(User).where(User.username == "clin1")).scalar_one()
        return round((aware(u.locked_until) - datetime.now(timezone.utc)).total_seconds() / 60)
    got = []
    for _ in range(3):
        bad_logins(); got.append(lock_minutes())
        with S() as s:
            s.execute(update(User).where(User.username == "clin1").values(locked_until=datetime.now(timezone.utc) - timedelta(minutes=1))); s.commit()
    assert got == [1, 2, 4]
    assert TestClient(app).post(LOGIN, json={"username": "clin1", "password": PW}).status_code == 200
    with S() as s: assert s.execute(select(User).where(User.username == "clin1")).scalar_one().lock_level == 0

def test_admin_unlock(env):
    adm, clin = login_as(env, "admin1"), login_as(env, "clin1")
    assert bad_logins() == [401] * 5
    assert TestClient(app).post(LOGIN, json={"username": "clin1", "password": PW}).status_code == 401
    assert clin.post("/api/v1/auth/users/clin1/unlock").status_code == 403
    assert adm.post("/api/v1/auth/users/nadie/unlock").status_code == 404
    assert adm.post("/api/v1/auth/users/clin1/unlock").status_code == 204
    assert TestClient(app).post(LOGIN, json={"username": "clin1", "password": PW}).status_code == 200
    with env[1]() as s:
        e = s.execute(select(AuditLog).where(AuditLog.event_type == "user_unlocked")).scalar_one()
    assert e.summary["username"] == "clin1" and e.summary["was_locked"] is True

# --- M-5: usuarios desconocidos e IP ---
def test_unknown_user_is_audited_without_storing_the_name(env):
    c, S = env
    for name in ("fantasma", "fantasma", "otro-fantasma"): assert c.post(LOGIN, json={"username": name, "password": "x" * 12}).status_code == 401
    with S() as s: rows = s.execute(select(AuditLog).where(AuditLog.event_type == "login_unknown_user").order_by(AuditLog.seq)).scalars().all()
    assert len(rows) == 3 and all(r.actor_id == "anonymous" and r.summary["ip"] for r in rows)
    assert "fantasma" not in json.dumps([r.summary for r in rows])
    d = [r.summary["username_digest"] for r in rows]; assert len(d[0]) == 32 and d[0] == d[1] != d[2]
    assert login_as(env, "aud1").get("/api/v1/audit/verify").json()["valid"] is True

def test_login_events_carry_ip(env):
    bad_logins(n=1); login_as(env, "clin1")
    with env[1]() as s:
        rows = s.execute(select(AuditLog).where(AuditLog.event_type.in_(["login_failed", "login_success"]))).scalars().all()
    assert rows and all(r.summary.get("ip") for r in rows)

@pg_only
def test_parallel_wrong_current_password_cannot_exceed_lockout(env):
    _, S = env; cl = login_as(env, "clin1")
    def attempt(_):
        c = TestClient(app); c.cookies.update(cl.cookies); c.headers["X-CSRF-Token"] = cl.headers["X-CSRF-Token"]
        return c.post(CHG, json={"current_password": "incorrecta-123456", "new_password": NEW}).status_code
    with ThreadPoolExecutor(12) as ex: codes = list(ex.map(attempt, range(12)))
    assert set(codes) == {403}
    ev = events(S); assert ev.count("password_change_failed") == 4 and ev.count("account_locked") == 1
