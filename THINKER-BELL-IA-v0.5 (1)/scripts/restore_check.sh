#!/usr/bin/env bash
# Restaura en una BD VACÍA, verifica firma, conteos y ambas cadenas de auditoría. NUNCA apuntar a producción.
# Uso: PGHOST=… PGDATABASE=bd_vacia PGUSER=<propietario> (PGPASSWORD/PGPASSFILE) BACKUP_SIGNER_FPR=<huella del firmante> \
#      AUDIT_HMAC_KEY(_FILE)=… [ANCHOR_FILE=anclas.jsonl] scripts/restore_check.sh copia.dump.gpg
set -euo pipefail
: "${PGHOST:?}" "${PGDATABASE:?}" "${PGUSER:?}" "${BACKUP_SIGNER_FPR:?}"
: "${AUDIT_HMAC_KEY:-${AUDIT_HMAC_KEY_FILE:?define AUDIT_HMAC_KEY o AUDIT_HMAC_KEY_FILE}}"
ENC="${1:?Indica el archivo .dump.gpg}"
umask 077; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

( cd "$(dirname "$ENC")" && sha256sum -c "$(basename "$ENC").sha256" )
gpg --batch --status-fd 3 --decrypt -o "$TMP/db.dump" "$ENC" 3>"$TMP/status"     # falla si la firma es inválida
awk -v f="$BACKUP_SIGNER_FPR" '$2=="VALIDSIG" && ($3==f || $NF==f){ok=1} END{exit !ok}' "$TMP/status" \
  || { echo "Firma ausente o de otro firmante: abortado." >&2; exit 1; }

n="$(psql -Atc "select count(*) from pg_tables where schemaname='public'")"
[ "$n" = "0" ] || { echo "La BD destino no está vacía ($n tablas): abortado." >&2; exit 1; }
pg_restore --no-owner --exit-on-error --dbname="$PGDATABASE" "$TMP/db.dump"

for t in users patients triage_evaluations audit_logs access_logs; do echo -n "$t: "; psql -Atc "select count(*) from $t"; done
export DATABASE_URL="postgresql+psycopg://${PGUSER}@${PGHOST}:${PGPORT:-5432}/${PGDATABASE}" APP_ENV=development   # la contraseña viaja por PGPASSWORD/PGPASSFILE
A=${ANCHOR_FILE:+--anchor-file "$ANCHOR_FILE"}
python3 -m backend.app.cli verify-audit --chain audit  $A
python3 -m backend.app.cli verify-audit --chain access $A
echo "Restauración verificada."
