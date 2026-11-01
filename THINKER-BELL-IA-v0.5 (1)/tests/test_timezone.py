from datetime import date, datetime, timezone
import pytest
from sqlalchemy import select, update
from backend.app.db.models import TriageEvaluation
from backend.app.services.timeutil import as_utc, day_end_utc, day_start_utc
from tests.conftest import CTX, login_as

UTC = timezone.utc
V = {"respiratory_rate": 16, "oxygen_saturation": 97, "supplemental_oxygen": False, "spo2_scale_2": False,
     "systolic_bp": 120, "heart_rate": 78, "consciousness": "A", "temperature": 36.8}

def test_day_bounds_and_naive_datetimes():
    assert day_start_utc(date(2026, 10, 28)) == datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
    assert day_end_utc(date(2026, 10, 28)) == datetime(2026, 10, 29, 5, 0, tzinfo=UTC)
    day_end_utc(date.max)                                           # no debe lanzar OverflowError
    assert as_utc(datetime(2026, 1, 1, 12)).tzinfo is UTC and as_utc(datetime(2026, 1, 1, tzinfo=UTC)).hour == 0

def _seed(env, times):
    c, S = env
    clin = login_as(env, "clin1")
    assert clin.post("/api/v1/patients", json={"patient_id": "SYN-1", "full_name": "S", "age": 40, "gender": "unknown"}).status_code == 201
    for _ in times: assert clin.post("/api/v1/triage/evaluate", json={"patient_id": "SYN-1", "vitals": V, **CTX}).status_code == 201
    with S() as s:
        ids = s.execute(select(TriageEvaluation.id).order_by(TriageEvaluation.timestamp)).scalars().all()
        for i, t in zip(ids, times): s.execute(update(TriageEvaluation).where(TriageEvaluation.id == i).values(timestamp=t))
        s.commit()
    return login_as(env, "aud1")

TIMES = [datetime(2026, 10, 28, 4, 59, 59, tzinfo=UTC),   # 27-oct 23:59:59 Bogotá
         datetime(2026, 10, 29, 2, 30, tzinfo=UTC),       # 28-oct 21:30 (en UTC ya es 29)
         datetime(2026, 10, 29, 4, 59, 59, tzinfo=UTC),   # 28-oct 23:59:59
         datetime(2026, 10, 29, 5, 0, tzinfo=UTC)]        # 29-oct 00:00:00

def test_dashboard_groups_by_bogota_day(env):
    aud = _seed(env, TIMES)
    got = {d["day"]: d["count"] for d in aud.get("/api/v1/dashboard/summary").json()["per_day"]}
    assert got == {"2026-10-27": 1, "2026-10-28": 2, "2026-10-29": 1}

@pytest.mark.parametrize("params,total", [({"date_from": "2026-10-28", "date_to": "2026-10-28"}, 2),
                                          ({"date_from": "2026-10-29"}, 1), ({"date_to": "2026-10-27"}, 1),
                                          ({"date_from": "2026-10-27", "date_to": "2026-10-29"}, 4), ({"date_to": "9999-12-31"}, 4)])
def test_date_filters_use_bogota_days(env, params, total):
    aud = _seed(env, TIMES)
    assert aud.get("/api/v1/triage/evaluations", params=params).json()["total"] == total

def test_timestamps_are_returned_with_a_zone(env):
    aud = _seed(env, TIMES)
    assert all(x["timestamp"].endswith(("Z", "+00:00")) for x in aud.get("/api/v1/triage/evaluations").json()["items"])
