from datetime import date, timedelta
import pytest
from sqlalchemy import select, update
from backend.app.db.models import AuditLog, TriageEvaluation
from clinical.age import age_on, today_bogota
from clinical.special_populations import build_alerts
from tests.conftest import CTX, login_as

V = {"respiratory_rate": 8, "oxygen_saturation": 97, "supplemental_oxygen": False, "spo2_scale_2": False,
     "systolic_bp": 120, "heart_rate": 78, "consciousness": "A", "temperature": 36.8}    # puntaje 3
EVAL = "/api/v1/triage/evaluate"

def years_ago(n: int) -> date:
    t = today_bogota()
    try: return t.replace(year=t.year - n)
    except ValueError: return t.replace(year=t.year - n, day=28)      # hoy es 29-feb

def mk(clin, pid="SYN-1", **over):
    return clin.post("/api/v1/patients", json={"patient_id": pid, "full_name": "Sintético", "gender": "unknown", **over})

def ev(clin, pid="SYN-1", **ctx):
    return clin.post(EVAL, json={"patient_id": pid, "vitals": V, **{**CTX, **ctx}})

# --- edad ---
@pytest.mark.parametrize("birth,on,age", [
    (date(2010, 6, 15), date(2026, 6, 14), 15), (date(2010, 6, 15), date(2026, 6, 15), 16),
    (date(2012, 2, 29), date(2026, 2, 28), 13), (date(2012, 2, 29), date(2026, 3, 1), 14), (date(2000, 1, 1), date(2000, 1, 1), 0)])
def test_age_on(birth, on, age): assert age_on(birth, on) == age

def test_patient_birth_date_rules(env):
    clin = login_as(env, "clin1")
    assert mk(clin, "A", birth_date=str(today_bogota() + timedelta(days=1))).status_code == 422     # futura
    assert mk(clin, "B", birth_date=str(years_ago(30)), age=99).status_code == 422                   # incoherente
    assert mk(clin, "C").status_code == 422                                                           # ni edad ni fecha
    assert mk(clin, "D", birth_date=20000101).status_code == 422                                      # no-cadena
    assert mk(clin, "E", birth_date=str(years_ago(130))).status_code == 422                           # implausible
    r = mk(clin, "F", birth_date=str(years_ago(30))); assert r.status_code == 201 and r.json()["age"] == 30

# --- bloqueo pediátrico ---
def test_minor_is_blocked_audited_and_routed(env):
    clin = login_as(env, "clin1")
    assert mk(clin, age=15).status_code == 201
    r = ev(clin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "NEWS2_NOT_APPLICABLE"
    assert r.json()["detail"]["protocol_required"] == "PEDIATRICO_INSTITUCIONAL"
    with env[1]() as s:
        e = s.execute(select(AuditLog).where(AuditLog.event_type == "triage_blocked_age")).scalar_one()
        assert e.patient_id == "SYN-1" and e.summary["age_basis"] == "recorded_static"
        assert s.execute(select(TriageEvaluation)).first() is None                  # no se guardó ninguna evaluación
    assert login_as(env, "aud1").get("/api/v1/audit/verify").json()["valid"] is True

def test_birth_date_decides_the_boundary(env):
    clin = login_as(env, "clin1")
    mk(clin, "ADULT", birth_date=str(years_ago(16)))                                  # hoy cumple 16
    mk(clin, "MINOR", birth_date=str(years_ago(16) + timedelta(days=1)))              # cumple 16 mañana
    assert ev(clin, "ADULT").status_code == 201
    assert ev(clin, "MINOR").status_code == 422

# --- contexto y alertas ---
def test_valid_context_is_accepted(env):
    clin = login_as(env, "clin1"); mk(clin, age=40)
    r = ev(clin); assert r.status_code == 201 and r.json()["alerts"] == []

@pytest.mark.parametrize("bad", [{"pregnancy": "maybe"}, {"pregnancy": True}, {"spinal_cord_injury": 1}, {"spinal_cord_injury": "false"}])
def test_context_rejects_loose_values(env, bad):
    clin = login_as(env, "clin1"); mk(clin, age=40)
    assert ev(clin).status_code == 201                                                # control: el payload base es válido
    assert ev(clin, **bad).status_code == 422

@pytest.mark.parametrize("missing", ["pregnancy", "spinal_cord_injury"])
def test_context_fields_are_required(env, missing):
    clin = login_as(env, "clin1"); mk(clin, age=40)
    body = {"patient_id": "SYN-1", "vitals": V, **{k: v for k, v in CTX.items() if k != missing}}
    assert clin.post(EVAL, json=body).status_code == 422

def test_alerts_do_not_change_the_score(env):
    clin = login_as(env, "clin1"); mk(clin, age=30)
    base = ev(clin).json()
    both = ev(clin, pregnancy="yes", spinal_cord_injury=True).json()
    assert (both["total_score"], both["clinical_risk"], both["parameter_scores"]) == (base["total_score"], base["clinical_risk"], base["parameter_scores"])
    assert {a["code"]: a["severity"] for a in both["alerts"]} == {"PREGNANCY_NEWS2_NOT_VALIDATED": "hard", "SPINAL_CORD_INJURY_BASELINE": "hard"}
    assert [a["code"] for a in ev(clin, pregnancy="unknown").json()["alerts"]] == ["PREGNANCY_UNKNOWN"]

def test_alerts_are_persisted_and_returned_on_read(env):
    clin = login_as(env, "clin1"); mk(clin, age=30)
    eid = ev(clin, spinal_cord_injury=True).json()["evaluation_id"]
    got = login_as(env, "aud1").get(f"/api/v1/triage/evaluations/{eid}").json()
    assert got["context"]["spinal_cord_injury"] is True and got["alerts"][0]["code"] == "SPINAL_CORD_INJURY_BASELINE"

def test_removing_alerts_from_the_record_is_detected(env):
    clin = login_as(env, "clin1"); mk(clin, age=30); ev(clin, pregnancy="yes")
    with env[1]() as s:
        s.execute(update(TriageEvaluation).values(context={})); s.commit()           # borrar lo que el clínico vio
    assert login_as(env, "aud1").get("/api/v1/audit/verify").json()["valid"] is False

def test_alert_catalogue_is_well_formed():
    alerts = build_alerts("yes", True) + build_alerts("unknown", False)
    assert len({a["code"] for a in alerts}) == len(alerts) and all(a["text"] and a["severity"] in ("hard", "soft") for a in alerts)
    assert build_alerts("no", False) == []

def test_auditor_does_not_see_birth_date(env):
    clin, aud = login_as(env, "clin1"), login_as(env, "aud1")
    mk(clin, birth_date=str(years_ago(40)))
    assert clin.get("/api/v1/patients/SYN-1").json()["birth_date"] == str(years_ago(40))
    assert aud.get("/api/v1/patients/SYN-1").json()["birth_date"] is None
