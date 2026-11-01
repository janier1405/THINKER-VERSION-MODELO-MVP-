#!/usr/bin/env bash
# Genera los secretos de producción en ./secrets (se niega a sobrescribir). Los certificados TLS los pones tú.
set -euo pipefail
D=secrets
[ -e "$D/jwt_secret" ] && { echo "secrets/ ya existe; no se sobrescribe." >&2; exit 1; }
mkdir -p "$D"; chmod 700 "$D"      # el directorio protege; los archivos son 0444 para que los lea el usuario 'app' del contenedor
umask 022
g() { python3 -c "import secrets;print(secrets.token_urlsafe(${1:-32}),end='')"; }
SUP=$(g); OWN=$(g); APP=$(g)
printf %s "$SUP" > $D/pg_super_password
printf %s "$OWN" > $D/pg_owner_password
printf %s "$APP" > $D/tb_app_password
g > $D/tb_backup_password
printf %s "postgresql+psycopg://tb_owner:$OWN@db:5432/thinkerbell" > $D/database_url_owner
printf %s "postgresql+psycopg://tb_app:$APP@db:5432/thinkerbell"   > $D/database_url_app
g 48 > $D/jwt_secret
g 48 > $D/audit_hmac_key
echo "Listo. Copia tu certificado a $D/tls_fullchain y tu clave a $D/tls_privkey (chmod 644)."
echo "Respalda audit_hmac_key FUERA del servidor y de las copias de la BD: sin ella la cadena no se puede verificar."
