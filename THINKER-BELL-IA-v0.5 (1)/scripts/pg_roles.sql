-- Roles de BD con MÍNIMO privilegio (tb_app para la aplicación, tb_backup para copias).
-- Uso (como propietario, tras `alembic upgrade head`; idempotente, repetir tras cada migración):
--   psql -v ON_ERROR_STOP=1 -v db=thinkerbell -f scripts/pg_roles.sql
-- Las contraseñas se leen de archivos montados como secretos; no aparecen en argv.
-- Si el servidor tiene log_statement='all', las sentencias CREATE/ALTER ROLE quedarían en su log: usar 'ddl' o 'none'.
\if :{?app_password_file}
\else
  \set app_password_file /run/secrets/tb_app_password
\endif
\if :{?backup_password_file}
\else
  \set backup_password_file /run/secrets/tb_backup_password
\endif
\set app_password `cat :app_password_file`
\set backup_password `cat :backup_password_file`

SELECT format('CREATE ROLE tb_app LOGIN PASSWORD %L', :'app_password')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tb_app') \gexec
SELECT format('ALTER ROLE tb_app PASSWORD %L', :'app_password') \gexec
ALTER ROLE tb_app SET idle_in_transaction_session_timeout = '30s';   -- una petición colgada no retiene locks de fila/advisory

SELECT format('CREATE ROLE tb_backup LOGIN PASSWORD %L', :'backup_password')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tb_backup') \gexec
SELECT format('ALTER ROLE tb_backup PASSWORD %L', :'backup_password') \gexec
ALTER ROLE tb_backup SET default_transaction_read_only = on;

-- Un propietario con CREATEROLE (no superusuario) no puede ejecutar ALTER ROLE ... NOSUPERUSER en PostgreSQL 16.
-- Los roles nacen sin privilegios (valores por defecto) y aquí se VERIFICA que sigan así: si alguien los elevó, el script falla.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('tb_app','tb_backup')
             AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN
    RAISE EXCEPTION 'tb_app/tb_backup tienen atributos privilegiados: corrígelo con un superusuario';
  END IF;
END $$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM tb_app;               -- fail-closed: solo lo concedido abajo
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM tb_backup;
GRANT CONNECT ON DATABASE :"db" TO tb_app, tb_backup;
GRANT USAGE ON SCHEMA public TO tb_app, tb_backup;
GRANT SELECT, INSERT ON users, patients, triage_evaluations, audit_logs, access_logs TO tb_app;
GRANT UPDATE (failed_attempts, locked_until, lock_level, session_version, is_active,
              password_hash, must_change_password, password_changed_at) ON users TO tb_app;   -- ni role ni username
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tb_backup;
