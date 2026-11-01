"""Uso: PYTHONPATH=. python scripts/export_openapi.py > frontend/openapi.json
En producción /openapi.json está apagado, así que el esquema se vuelca sin levantar el servidor."""
import json, os, sys
os.environ.setdefault("APP_ENV", "development")
from backend.app.main import app
sys.stdout.write(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
