import json
from pathlib import Path
from fastapi.routing import APIRoute
from backend.app.main import app

R = Path(__file__).resolve().parents[1]

def test_committed_openapi_is_current():
    committed = json.loads((R / "frontend" / "openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(app.openapi())), \
        "Contrato desfasado. Ejecuta: PYTHONPATH=. python scripts/export_openapi.py > frontend/openapi.json && (cd frontend && npm run gen:api)"

def test_every_api_route_declares_a_response_model():
    missing = [f"{sorted(r.methods)} {r.path}" for r in app.routes
               if isinstance(r, APIRoute) and r.path.startswith("/api/") and r.status_code != 204 and r.response_model is None]
    assert not missing, missing

def test_strict_request_schemas_forbid_extra_fields():
    # el chequeo de typos en compilación (TypeScript) depende de esto
    schemas = app.openapi()["components"]["schemas"]
    for name in ("VitalsIn", "EvaluateIn", "PatientIn", "LoginIn", "UserCreate"):
        assert schemas[name].get("additionalProperties") is False, name
