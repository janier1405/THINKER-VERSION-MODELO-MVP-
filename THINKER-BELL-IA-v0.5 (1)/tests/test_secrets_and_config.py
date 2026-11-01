import os, subprocess, sys
from backend.app.core.secrets import secret

def test_secret_reads_file_strips_and_falls_back(tmp_path, monkeypatch):
    f = tmp_path / "s"; f.write_text("valor\n")
    monkeypatch.setenv("X_TEST", "desde-env"); monkeypatch.setenv("X_TEST_FILE", str(f))
    assert secret("X_TEST") == "valor"                     # el archivo gana y se recorta
    monkeypatch.delenv("X_TEST_FILE"); assert secret("X_TEST") == "desde-env"
    assert secret("NO_EXISTE_XYZ", "d") == "d" and secret("NO_EXISTE_XYZ") is None

def _import_session(**extra):
    base = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "DATABASE_URL_FILE")}
    return subprocess.run([sys.executable, "-c", "import backend.app.db.session"], env={**base, **extra}, capture_output=True, text=True)

def test_production_requires_postgres_url():
    r = _import_session(APP_ENV="production"); assert r.returncode != 0 and "DATABASE_URL" in r.stderr
    r = _import_session(APP_ENV="production", DATABASE_URL="sqlite:///x.db"); assert r.returncode != 0
    assert _import_session(APP_ENV="production", DATABASE_URL="postgresql+psycopg://u:p@h/db").returncode == 0
    assert _import_session(APP_ENV="development").returncode == 0      # dev sigue usando SQLite por defecto
