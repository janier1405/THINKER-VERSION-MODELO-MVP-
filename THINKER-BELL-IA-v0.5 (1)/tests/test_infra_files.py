from pathlib import Path
R = Path(__file__).resolve().parents[1]

def test_prod_requirements_are_hashed_and_free_of_dev_tools():
    t = (R / "requirements.txt").read_text().lower()
    assert "--hash=sha256:" in t and "pytest" not in t and "httpx" not in t

def test_dockerfile_non_root_healthcheck_no_latest():
    d = (R / "Dockerfile").read_text()
    assert "USER " in d and "HEALTHCHECK" in d and "--require-hashes" in d and ":latest" not in d and "pytest" not in d

def test_compose_has_no_plaintext_secrets_or_db_port():
    c = (R / "docker-compose.yml").read_text()
    for plain in ("POSTGRES_PASSWORD:", "JWT_SECRET:", "AUDIT_HMAC_KEY:", "DATABASE_URL:"):
        assert plain not in c, plain
    assert "5432:" not in c and "8000:8000" not in c

def test_dockerignore_excludes_secrets():
    assert "secrets/" in (R / ".dockerignore").read_text()

def test_security_headers_not_overridden_per_location():
    conf = (R / "proxy/conf.d/default.conf").read_text()
    assert "X-Forwarded-For $remote_addr" in (R / "proxy/snippets/proxy_params.conf").read_text()
    directives = [l.strip() for l in conf.splitlines() if l.strip().startswith("add_header")]   # ignora comentarios
    assert directives == ['add_header Cache-Control "no-cache" always;'] and "security_headers.conf" in conf
