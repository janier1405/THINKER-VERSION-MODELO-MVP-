#!/usr/bin/env bash
# Copia lógica CIFRADA y FIRMADA con el rol tb_backup (solo lectura). Sin secretos en argv.
# Uso: PGHOST=… PGDATABASE=… PGUSER=tb_backup (PGPASSWORD_FILE o ~/.pgpass) \
#      BACKUP_RECIPIENT=<HUELLA GPG> BACKUP_SIGNING_KEY=<id de clave> scripts/backup.sh [salida.dump.gpg]
set -euo pipefail
: "${PGHOST:?}" "${PGDATABASE:?}" "${PGUSER:?}"
: "${BACKUP_RECIPIENT:?huella de la clave pública de quien podrá restaurar}" "${BACKUP_SIGNING_KEY:?clave GPG de firma}"
if [ -n "${PGPASSWORD_FILE:-}" ]; then PGPASSWORD="$(cat "$PGPASSWORD_FILE")"; export PGPASSWORD; fi
umask 077
OUT="${1:-backup_$(date -u +%Y%m%dT%H%M%SZ).dump.gpg}"
trap 'rm -f "$OUT.partial"' ERR
# --trust-model always es aceptable aquí solo porque el destinatario se fija por huella
pg_dump --format=custom --no-owner \
  | gpg --batch --yes --trust-model always --encrypt --sign --local-user "$BACKUP_SIGNING_KEY" \
        --recipient "$BACKUP_RECIPIENT" -o "$OUT.partial"
mv "$OUT.partial" "$OUT"
( cd "$(dirname "$OUT")" && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256" )   # detecta corrupción, NO manipulación
echo "Copia cifrada y firmada: $OUT"
