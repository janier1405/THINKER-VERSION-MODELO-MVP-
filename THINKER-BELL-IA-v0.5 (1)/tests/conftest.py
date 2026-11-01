import os
os.environ.setdefault("APP_ENV", "development")   # antes de importar la app
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.core.security import hash_password
from backend.app.db.models import User
from backend.app.db.session import Base, get_db
from backend.app.main import app

PW = "contrasena-de-prueba-123"
CTX = {"pregnancy": "no", "spinal_cord_injury": False}   # contexto clínico obligatorio de /triage/evaluate

@pytest.fixture()
def env():
    url = os.getenv("TEST_DATABASE_URL")  # p. ej. postgresql+psycopg://tb:...@localhost/tb_test
    engine = create_engine(url) if url else create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if url: Base.metadata.drop_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    def override():
        db = Session()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db] = override
    with Session() as s:
        for name, role in (("admin1", "admin"), ("clin1", "clinician"), ("aud1", "auditor")):
            s.add(User(username=name, password_hash=hash_password(PW), role=role))
        s.commit()
    with TestClient(app) as c:
        yield c, Session
    app.dependency_overrides.clear(); Base.metadata.drop_all(bind=engine); engine.dispose()

def login_as(env, username):
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"username": username, "password": PW}).status_code == 200
    c.headers["X-CSRF-Token"] = c.cookies.get("tb_csrf")  # como hace el frontend
    return c
