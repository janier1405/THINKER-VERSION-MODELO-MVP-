import os, secrets
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from backend.app.core.secrets import secret

APP_ENV = os.getenv("APP_ENV")
if APP_ENV not in ("development", "production"):  # fail-closed: sin valor por defecto
    raise RuntimeError("Define APP_ENV=development|production explícitamente.")
_env_secret = secret("JWT_SECRET")
if APP_ENV == "production":  # fail-fast: no arrancar con configuración insegura
    if not _env_secret or len(_env_secret) < 32: raise RuntimeError("Producción exige JWT_SECRET de al menos 32 caracteres.")
    if os.getenv("COOKIE_SECURE", "false").lower() != "true": raise RuntimeError("Producción exige COOKIE_SECURE=true (HTTPS).")
_audit = secret("AUDIT_HMAC_KEY")
if APP_ENV == "production" and (not _audit or len(_audit.encode()) < 32):
    raise RuntimeError("Producción exige AUDIT_HMAC_KEY de al menos 32 bytes.")
# En desarrollo la clave es pública y constante: la cadena de dev NO es infalsificable.
AUDIT_KEY: bytes = (_audit or "dev-only-audit-key-NOT-FOR-PRODUCTION").encode()
SECRET = _env_secret or secrets.token_urlsafe(48)  # efímero en desarrollo
SESSION_MINUTES = int(os.getenv("SESSION_MINUTES", "60"))
COOKIE, CSRF_COOKIE = "tb_session", "tb_csrf"
_ph = PasswordHasher()
_DUMMY = _ph.hash("dummy-password-for-timing")

def hash_password(p: str) -> str: return _ph.hash(p)
def verify_password(h: str | None, p: str) -> bool:
    try: return _ph.verify(h or _DUMMY, p) and h is not None
    except (VerifyMismatchError, InvalidHashError): return False

def password_problem(new: str, current: str, username: str) -> str | None:
    """Reglas mínimas. No hay lista de contraseñas filtradas (pendiente); no presentar esto como política completa."""
    if new == current: return "La nueva contraseña debe ser distinta de la actual."
    if username.lower() in new.lower(): return "La contraseña no puede contener el nombre de usuario."
    if len(set(new)) < 5: return "La contraseña es demasiado repetitiva."
    return None

def make_token(user_id: str, version: int, csrf: str) -> str:
    return jwt.encode({"sub": user_id, "v": version, "csrf": csrf, "exp": datetime.now(timezone.utc) + timedelta(minutes=SESSION_MINUTES)}, SECRET, algorithm="HS256")
def read_token(t: str) -> dict | None:
    try:
        d = jwt.decode(t, SECRET, algorithms=["HS256"]); return d if "sub" in d else None
    except jwt.PyJWTError: return None
