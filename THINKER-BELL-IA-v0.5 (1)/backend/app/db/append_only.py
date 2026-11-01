"""Defensa en profundidad: la BD rechaza UPDATE/DELETE/TRUNCATE sobre las tablas de evidencia.
Protege contra bugs o inyección SQL de la app. NO protege contra el propietario de la BD (puede hacer DISABLE TRIGGER)."""
TABLES = ("audit_logs", "access_logs", "triage_evaluations")
_NO_TRUNCATE = ("audit_logs", "access_logs")   # triage_evaluations lo referencia una FK; PostgreSQL ya impide su TRUNCATE

FUNCTION = """CREATE OR REPLACE FUNCTION tb_forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION USING MESSAGE = 'append-only: ' || TG_OP || ' prohibido sobre ' || TG_TABLE_NAME, ERRCODE = '42501';
END $$"""

def _mutation(t: str) -> str:
    return (f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} "
            f"FOR EACH ROW EXECUTE FUNCTION tb_forbid_mutation()")

def _truncate(t: str) -> str:
    return (f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION tb_forbid_mutation()")

STATEMENTS = [FUNCTION, *[_mutation(t) for t in TABLES], *[_truncate(t) for t in _NO_TRUNCATE]]
DROP_STATEMENTS = [*[f"DROP TRIGGER IF EXISTS {t}_append_only ON {t}" for t in TABLES],
                   *[f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}" for t in _NO_TRUNCATE],
                   "DROP FUNCTION IF EXISTS tb_forbid_mutation()"]
