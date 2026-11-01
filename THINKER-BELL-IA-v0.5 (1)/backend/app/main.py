import logging, os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.api.v1.endpoints import auth, patients, triage
from backend.app.core.security import APP_ENV
from backend.app.db import models  # noqa: F401
from backend.app.db.session import Base, engine, get_db

log = logging.getLogger("thinkerbell")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine.dialect.name == "postgresql":   # las cadenas de auditoría solo son correctas bajo READ COMMITTED
        with engine.connect() as c:
            iso = c.execute(text("SHOW transaction_isolation")).scalar()
        if iso != "read committed":
            raise RuntimeError(f"Las cadenas de auditoría exigen READ COMMITTED (actual: {iso}).")
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true" and APP_ENV != "production":  # solo desarrollo; usar Alembic
        Base.metadata.create_all(bind=engine)
    yield

prod = APP_ENV == "production"
app = FastAPI(title="Thinker Bell API", version="0.5.0", lifespan=lifespan, docs_url=None if prod else "/docs", redoc_url=None, openapi_url=None if prod else "/openapi.json",
              description="API de apoyo a evaluación NEWS2. Datos sintéticos. Reglas clínicas PENDIENTES DE VALIDACIÓN.")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-CSRF-Token"])

@app.middleware("http")
async def security_headers(request: Request, call_next):
    r = await call_next(request)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
    if request.url.path.startswith("/api"): r.headers["Cache-Control"] = "no-store"  # respuestas clínicas no cacheables
    return r

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("Error no controlado: %s en %s %s", type(exc).__name__, request.method, request.url.path)  # sin cuerpo ni datos clínicos
    return JSONResponse({"detail": "Error interno."}, status_code=500)

for r in (auth.router, patients.router, triage.router): app.include_router(r, prefix="/api/v1")

@app.get("/health")
def health(): return {"status": "ok", "service": "thinker-bell-api", "version": app.version}

@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1 FROM users LIMIT 1"))    # comprueba conexión Y permisos de tb_app
    except Exception:
        log.error("readiness: la base de datos no responde")
        return JSONResponse({"status": "unavailable"}, status_code=503)   # sin detalle: puede contener host o credenciales
    return {"status": "ok"}
