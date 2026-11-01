import hmac, os, secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.core.security import (COOKIE, CSRF_COOKIE, SESSION_MINUTES, hash_password, make_token,
                                       password_problem, read_token, verify_password)
from backend.app.db.models import User
from backend.app.db.session import get_db
from backend.app.schemas.out import UserOut
from backend.app.schemas.triage import LoginIn, PasswordChange, UserCreate
from backend.app.services.audit import append_audit, client_ip, keyed_digest

router = APIRouter(prefix="/auth", tags=["Auth"])
MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", "5"))
LOCK_BASE_MIN = int(os.getenv("LOGIN_LOCK_BASE_MINUTES", "1")); LOCK_MAX_MIN = int(os.getenv("LOGIN_LOCK_MAX_MINUTES", "30"))
SAFE = ("GET", "HEAD", "OPTIONS")
BAD_LOGIN = "Credenciales inválidas o cuenta bloqueada temporalmente."   # mensaje único: no revela si el usuario existe
_aware = lambda d: d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def _lock_minutes(level: int) -> int:
    return min(LOCK_BASE_MIN * 2 ** min(max(level, 0), 20), LOCK_MAX_MIN)   # el tope del exponente evita enteros enormes

def _session(request: Request, db: Session) -> User:
    tok = request.cookies.get(COOKIE); data = read_token(tok) if tok else None
    user = db.get(User, data["sub"]) if data else None
    # el rol y la versión de sesión se leen SIEMPRE de la BD, no del token
    if user is None or not user.is_active or data.get("v") != user.session_version: raise HTTPException(401, "No autenticado.")
    if request.method not in SAFE:  # CSRF: el token va ligado a la sesión (claim firmado) y debe repetirse en cabecera
        h = request.headers.get("x-csrf-token")
        if not h or not hmac.compare_digest(h, str(data.get("csrf", ""))): raise HTTPException(403, "Token CSRF ausente o inválido.")
    return user

def current_user_pending(request: Request, db: Session = Depends(get_db)) -> User:
    """Sesión válida aunque deba cambiar la contraseña: solo para /me y /change-password."""
    return _session(request, db)

def current_user(user: User = Depends(current_user_pending)) -> User:
    if user.must_change_password:
        raise HTTPException(403, {"code": "PASSWORD_CHANGE_REQUIRED", "message": "Debes cambiar tu contraseña antes de continuar."})
    return user

def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles: raise HTTPException(403, "Permiso insuficiente.")
        return user
    return dep

def _cookie_kw(): return dict(samesite="lax", max_age=SESSION_MINUTES * 60, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true")

def _issue_session(response: Response, user: User) -> None:
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(COOKIE, make_token(user.id, user.session_version, csrf), httponly=True, **_cookie_kw())
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **_cookie_kw())  # legible por JS a propósito (patrón double-submit)

def _register_failure(db: Session, user: User, now: datetime, ip: str | None, event: str = "login_failed") -> None:
    """Llamar con la fila del usuario BLOQUEADA (FOR UPDATE). Orden de locks: fila -> advisory."""
    user.failed_attempts += 1
    if user.failed_attempts >= MAX_FAILS:
        minutes = _lock_minutes(user.lock_level)
        user.locked_until, user.failed_attempts, user.lock_level = now + timedelta(minutes=minutes), 0, user.lock_level + 1
        append_audit(db, event_type="account_locked", actor_id=user.id, summary={"minutes": minutes, "level": user.lock_level, "ip": ip})
    else:
        append_audit(db, event_type=event, actor_id=user.id, summary={"ip": ip})

@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    now, ip = datetime.now(timezone.utc), client_ip(request)
    user = db.execute(select(User).where(User.username == body.username).with_for_update()).scalar_one_or_none()
    locked = bool(user and user.locked_until and _aware(user.locked_until) > now)
    ok = verify_password(user.password_hash if user else None, body.password)  # siempre se verifica (tiempo constante aprox.)
    if locked or not (ok and user and user.is_active):
        if user is None:      # visible para el auditor: permite detectar password spraying sin guardar el nombre probado
            append_audit(db, event_type="login_unknown_user", actor_id="anonymous",
                         summary={"username_digest": keyed_digest("username", body.username), "ip": ip}); db.commit()
        elif not locked:
            _register_failure(db, user, now, ip); db.commit()
        raise HTTPException(401, BAD_LOGIN)
    user.failed_attempts, user.locked_until, user.lock_level = 0, None, 0
    # must_change_password=true en este evento permite revisar quién entró con una clave que el admin conocía
    append_audit(db, event_type="login_success", actor_id=user.id, summary={"ip": ip, "must_change_password": user.must_change_password}); db.commit()
    _issue_session(response, user)
    return {"username": user.username, "role": user.role, "must_change_password": user.must_change_password}

@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    tok = request.cookies.get(COOKIE); data = read_token(tok) if tok else None
    user = db.get(User, data["sub"], with_for_update=True) if data else None
    if user and data.get("v") == user.session_version:
        user.session_version += 1  # revoca TODAS las sesiones emitidas; cerrar sesión es inocuo ante CSRF
        append_audit(db, event_type="logout", actor_id=user.id, summary={"ip": client_ip(request)}); db.commit()
    response.delete_cookie(COOKIE); response.delete_cookie(CSRF_COOKIE)

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user_pending)):
    return {"username": user.username, "role": user.role, "must_change_password": user.must_change_password}

@router.post("/change-password", response_model=UserOut)
def change_password(body: PasswordChange, request: Request, response: Response,
                    pending: User = Depends(current_user_pending), db: Session = Depends(get_db)):
    now, ip = datetime.now(timezone.utc), client_ip(request)
    # populate_existing: la fila ya está en el identity map (la cargó la dependencia) y sin esto el bloqueo leería valores obsoletos
    user = db.get(User, pending.id, with_for_update=True, populate_existing=True)
    if user is None or not user.is_active: raise HTTPException(401, "No autenticado.")
    locked = bool(user.locked_until and _aware(user.locked_until) > now)
    ok = verify_password(user.password_hash, body.current_password)
    if locked or not ok:   # una sesión robada no puede adivinar la clave actual sin gastar el mismo contador de bloqueo
        if not locked: _register_failure(db, user, now, ip, event="password_change_failed"); db.commit()
        raise HTTPException(403, "La contraseña actual no es correcta o la cuenta está bloqueada temporalmente.")
    if (problem := password_problem(body.new_password, body.current_password, user.username)): raise HTTPException(422, problem)
    forced = user.must_change_password
    user.password_hash, user.must_change_password, user.password_changed_at = hash_password(body.new_password), False, now
    user.session_version += 1                                   # corta TODAS las demás sesiones
    user.failed_attempts, user.locked_until, user.lock_level = 0, None, 0
    append_audit(db, event_type="password_changed", actor_id=user.id, summary={"forced": forced, "ip": ip}); db.commit()
    _issue_session(response, user)                              # esta sesión continúa con versión y CSRF nuevos
    return {"username": user.username, "role": user.role, "must_change_password": False}

@router.post("/users", status_code=201, response_model=UserOut)
def create_user(body: UserCreate, request: Request, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role, must_change_password=True)
    db.add(user)
    try:
        db.flush(); append_audit(db, event_type="user_created", actor_id=admin.id,
                                 summary={"username": body.username, "role": body.role, "ip": client_ip(request)}); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "El usuario ya existe.")
    return {"username": user.username, "role": user.role, "must_change_password": True}

@router.post("/users/{username}/deactivate", status_code=204)
def deactivate_user(username: str, request: Request, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    u = db.execute(select(User).where(User.username == username).with_for_update()).scalar_one_or_none()
    if not u: raise HTTPException(404, "Usuario no encontrado.")
    if u.id == admin.id: raise HTTPException(409, "No puedes desactivar tu propia cuenta.")
    u.is_active, u.session_version = False, u.session_version + 1  # corta sesiones vigentes
    append_audit(db, event_type="user_deactivated", actor_id=admin.id, summary={"username": username, "ip": client_ip(request)}); db.commit()

@router.post("/users/{username}/unlock", status_code=204)
def unlock_user(username: str, request: Request, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    u = db.execute(select(User).where(User.username == username).with_for_update()).scalar_one_or_none()
    if not u: raise HTTPException(404, "Usuario no encontrado.")
    was_locked = bool(u.locked_until and _aware(u.locked_until) > datetime.now(timezone.utc))
    u.failed_attempts, u.locked_until, u.lock_level = 0, None, 0
    append_audit(db, event_type="user_unlocked", actor_id=admin.id, summary={"username": username, "was_locked": was_locked, "ip": client_ip(request)}); db.commit()
