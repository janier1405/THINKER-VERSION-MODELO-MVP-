#!/bin/sh
# Corre UNA sola vez, al inicializar un volumen vacío. El superusuario de arranque no lo usa nadie más.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE tb_owner LOGIN NOSUPERUSER CREATEROLE PASSWORD '$(cat /run/secrets/pg_owner_password)';
CREATE DATABASE thinkerbell OWNER tb_owner;
SQL
