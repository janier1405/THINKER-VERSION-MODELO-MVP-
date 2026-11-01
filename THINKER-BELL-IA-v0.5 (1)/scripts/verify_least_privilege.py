"""Verifica con el rol tb_app que la app funciona y que NO puede alterar evidencia ni escalar privilegios.
Nunca persiste nada de las pruebas negativas (rollback) y falla (exit 1) si algo prohibido se permite.
Uso: DATABASE_URL(_FILE)=<url de tb_app> VERIFY_USER=<clínico> VERIFY_PASSWORD=<clave> PYTHONPATH=. python scripts/verify_least_privilege.py"""
import os, sys
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from backend.app.db.session import SessionLocal
from backend.app.main import app

u, pw = os.environ["VERIFY_USER"], os.environ["VERIFY_PASSWORD"]
c = TestClient(app); assert c.post("/api/v1/auth/login", json={"username": u, "password": pw}).status_code == 200
c.headers["X-CSRF-Token"] = c.cookies["tb_csrf"]
assert c.post("/api/v1/patients", json={"patient_id": "PRIV-1", "full_name": "Sintético", "age": 50, "gender": "unknown"}).status_code in (201, 409)
v = {"respiratory_rate": 16, "oxygen_saturation": 97, "supplemental_oxygen": False, "spo2_scale_2": False,
     "systolic_bp": 120, "heart_rate": 70, "consciousness": "A", "temperature": 36.8}
assert c.post("/api/v1/triage/evaluate", json={"patient_id": "PRIV-1", "vitals": v, "pregnancy": "no", "spinal_cord_injury": False}).status_code == 201
print("flujo de la app con tb_app: OK")

MUST_FAIL = (
    "UPDATE audit_logs SET event_type='x'", "DELETE FROM audit_logs", "TRUNCATE audit_logs",
    "UPDATE access_logs SET action='x'", "DELETE FROM access_logs", "TRUNCATE access_logs",
    "UPDATE triage_evaluations SET total_score=0", "DELETE FROM triage_evaluations",
    "UPDATE users SET role='admin'", "UPDATE users SET username='x'", "DELETE FROM users",
    "DROP TABLE users", "CREATE TABLE tb_intruso(x int)",
)
MUST_WORK = ("UPDATE users SET failed_attempts = failed_attempts", "UPDATE users SET password_hash = password_hash",
             "SELECT count(*) FROM audit_logs")   # control positivo; el segundo es el riesgo residual aceptado
bad = []
for sql in MUST_FAIL:
    with SessionLocal() as s:
        try:
            s.execute(text(sql)); bad.append(sql); print("PERMITIDO (MAL):", sql)
        except ProgrammingError as e:
            print("denegado (bien):", sql, "|", str(e.orig).splitlines()[0][:70])
        finally:
            s.rollback()                       # jamás commit: si algo se permitió, no se persiste
for sql in MUST_WORK:
    with SessionLocal() as s:
        try: s.execute(text(sql)); print("permitido (bien):", sql)
        except ProgrammingError as e: bad.append(sql); print("DENEGADO (MAL):", sql, "|", str(e.orig).splitlines()[0][:70])
        finally: s.rollback()
sys.exit(1 if bad else 0)
