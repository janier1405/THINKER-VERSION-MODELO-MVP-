"""Comandos:
  create-admin --username NOMBRE            (contraseña por consola sin eco o TB_ADMIN_PASSWORD; se niega si ya existe un admin)
  anchor-audit [--chain audit|access]       imprime una línea JSON; envíala a un destino de solo-anexado (WORM/syslog remoto)
  verify-audit [--chain ...] [--anchor-file F]   verifica la cadena y, si hay ancla, que la cola no fue truncada
"""
import argparse, getpass, json, os, sys
from sqlalchemy import select
from backend.app.core.security import hash_password
from backend.app.db.models import User
from backend.app.db.session import SessionLocal
from backend.app.services.audit import make_anchor, verify_access_chain, verify_chain

def create_admin(username: str) -> int:
    pw = os.getenv("TB_ADMIN_PASSWORD") or getpass.getpass("Contraseña (mín. 12 caracteres): ")
    if len(pw) < 12: print("La contraseña debe tener al menos 12 caracteres."); return 1
    with SessionLocal() as db:
        if db.execute(select(User).where(User.role == "admin")).first(): print("Ya existe un administrador."); return 1
        db.add(User(username=username, password_hash=hash_password(pw), role="admin")); db.commit()
    print("Administrador creado."); return 0

def anchor(chain: str) -> int:
    with SessionLocal() as db: a = make_anchor(db, chain)
    if a is None: print("La cadena está vacía.", file=sys.stderr); return 1
    print(json.dumps(a, separators=(",", ":"))); return 0

def verify(chain: str, anchor_file: str | None) -> int:
    a = None
    if anchor_file:
        for line in open(anchor_file, encoding="utf-8"):
            if line.strip() and (d := json.loads(line)).get("chain") == chain: a = d   # el último de esa cadena
        if a is None: print(f"No hay ancla de la cadena '{chain}' en {anchor_file}.", file=sys.stderr); return 2
    with SessionLocal() as db:
        ok, bad = (verify_chain if chain == "audit" else verify_access_chain)(db, a)
    print(json.dumps({"chain": chain, "valid": ok, "first_invalid_seq": bad, "anchored": a is not None})); return 0 if ok else 1

def main() -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create-admin").add_argument("--username", required=True)
    for name in ("anchor-audit", "verify-audit"):
        p = sub.add_parser(name); p.add_argument("--chain", choices=("audit", "access"), default="audit")
        if name == "verify-audit": p.add_argument("--anchor-file")
    a = ap.parse_args()
    if a.cmd == "create-admin": return create_admin(a.username)
    return anchor(a.chain) if a.cmd == "anchor-audit" else verify(a.chain, a.anchor_file)

if __name__ == "__main__": sys.exit(main())
