import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from backend.app.core.secrets import secret

DATABASE_URL = secret("DATABASE_URL")
if os.getenv("APP_ENV") == "production":   # sin importar security.py: migrate no necesita JWT ni HMAC
    if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Producción exige DATABASE_URL de PostgreSQL (también vale DATABASE_URL_FILE).")
DATABASE_URL = DATABASE_URL or "sqlite:///./thinkerbell_dev.db"
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
