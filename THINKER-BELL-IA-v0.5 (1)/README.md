# Thinker Bell v0.5 (desarrollo)

Apoyo a la evaluación NEWS2 con historial y auditoría. **Solo datos sintéticos. Reglas NEWS2 PENDIENTES DE VALIDACIÓN CLÍNICA. No es diagnóstico, dispositivo médico autorizado ni sistema listo para uso clínico.** Sin IA y sin integración FHIR funcional (ver `docs/ROADMAP_FHIR_AI.md`).

> **Estado de cumplimiento:** `docs/REGULATORY_COMPLIANCE.md` es la única fuente de verdad sobre qué requisitos están implementados, parciales o ausentes. No hay base jurídica para tratar datos reales de pacientes (consentimiento, política de tratamiento, registro de bases de datos, incidentes): ver esa matriz antes de cualquier uso con datos reales.

## Estructura

```
backend/app/{core,db,schemas,services,api/v1/endpoints}   API FastAPI (auth, pacientes, triaje, auditoría)
backend/migrations/versions/0001…0006                      Alembic (0004 = triggers append-only, solo PostgreSQL)
clinical/                                                  Motor NEWS2, edad, alertas de poblaciones especiales (puro, sin BD)
interoperability/fhir/                                     Adaptador FHIR HEREDADO, NO conectado ni validado
frontend/                                                  React + TypeScript + Vite + Vitest (tipos generados desde OpenAPI)
scripts/                                                   pg_roles.sql, backup/restore, gen_secrets, verify_least_privilege, export_openapi
proxy/  db/init/                                           nginx (TLS, cabeceras, límite por IP) y bootstrap de PostgreSQL
tests/                                                     Pytest (SQLite y PostgreSQL)
docs/                                                      Matriz regulatoria, informe técnico, revisión de seguridad, verificación NEWS2, hoja de ruta
.github/workflows/ci.yml                                   CI (escrito; no ejecutado todavía en GitHub)
```

## Requisitos

Python 3.12, **Node ≥ 22.12** (lo exige Vitest 5 / Vite 7), PostgreSQL 16 (SQLite sirve para desarrollo rápido; las pruebas de concurrencia y triggers solo corren en PostgreSQL), `gpg` para las copias. Docker es opcional.

## Desarrollo local

```bash
# 1) Backend
python3 -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
export APP_ENV=development            # OBLIGATORIO: sin él la aplicación no arranca (a propósito)
export JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
export AUDIT_HMAC_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))")   # en dev hay una clave pública por defecto; no falsificable solo en producción

# 2) Base de datos: opción A SQLite (rápido)   export DATABASE_URL=sqlite:///./thinkerbell_dev.db
#    opción B PostgreSQL: export DATABASE_URL=postgresql+psycopg://usuario:clave@localhost:5432/tb_dev
alembic upgrade head
python -m backend.app.cli create-admin --username <nombre>     # pide contraseña ≥12 sin eco (o TB_ADMIN_PASSWORD)
uvicorn backend.app.main:app --port 8000                       # OpenAPI: http://localhost:8000/docs

# 3) Frontend
cd frontend && npm ci && npm run dev                           # http://localhost:5173 (proxy /api → :8000)
```

Los demás usuarios los crea el admin con `POST /api/v1/auth/users`; entran con una contraseña inicial que **deben cambiar en el primer inicio de sesión**. La interfaz aún no tiene pantalla de gestión de usuarios, ni de revisión de accesos (existe `GET /api/v1/audit/access-logs` para el rol auditor).

Cambios de política frente a v0.4 que conviene conocer: `LOGIN_LOCK_MINUTES` ya no existe (ahora `LOGIN_LOCK_BASE_MINUTES` / `LOGIN_LOCK_MAX_MINUTES`, backoff 1→30 min); `admin` y `auditor` no ven nombre, edad ni fecha de nacimiento (el admin puede hacer un acceso de emergencia registrado); `POST /triage/evaluate` exige `pregnancy` y `spinal_cord_injury`; los campos desconocidos en cualquier petición son un 422.

## Pruebas

```bash
pytest                                                                                  # SQLite en memoria
TEST_DATABASE_URL=postgresql+psycopg://tb:<clave>@localhost:5432/tb_test pytest         # PostgreSQL real: concurrencia, deadlocks, triggers
PGTZ=Asia/Tokyo TEST_DATABASE_URL=… pytest tests/test_timezone.py                       # la salida no depende de la zona de la sesión
cd frontend && npm test && npm run build                                                # Vitest + tsc estricto + build
```

**Regla del 401.** El backend usa 401 *solo* para «sesión inválida»; el cliente cierra la sesión al verlo (salvo en `/auth/login` y `/auth/me`). Un endpoint nuevo que devuelva 401 por otra razón expulsaría al usuario: usa 403 o 422.

**Contrato OpenAPI.** `frontend/openapi.json` y `frontend/src/api-types.ts` se versionan. Si cambias un esquema:

```bash
PYTHONPATH=. python scripts/export_openapi.py > frontend/openapi.json && (cd frontend && npm run gen:api)
```

`tests/test_openapi_contract.py` falla si quedan desfasados.

## Despliegue (checklist; no se ha desplegado nada)

1. Revisión jurídica y clínica completada y documentada (ver `docs/REGULATORY_COMPLIANCE.md` §10).
2. `bash scripts/gen_secrets.sh`; copiar el certificado a `secrets/tls_fullchain` y la clave a `secrets/tls_privkey` (`chmod 644`); `chmod +x db/init/01-owner.sh`; fijar las imágenes base por *digest*.
3. `export CORS_ORIGINS=https://<dominio>` y `docker compose up --build -d`. El orden es `db → migrate (propietario) → roles (propietario) → api (tb_app) → proxy`. `docker compose ps -a`: `migrate` y `roles` en `Exited (0)`; `db`, `api` y `proxy` en `healthy`.
4. `docker compose run --rm api python -m backend.app.cli create-admin --username <nombre>`.
5. Comprobar el mínimo privilegio con un clínico de prueba: `docker compose run --rm -e VERIFY_USER=… -e VERIFY_PASSWORD=… api python scripts/verify_least_privilege.py` (debe salir con 0).
6. **Respaldar `audit_hmac_key` fuera del servidor y de las copias.** Sin ella la cadena de auditoría no se puede verificar; si se filtra, quien la tenga puede falsificarla.
7. Programar el ancla externa (`python -m backend.app.cli anchor-audit | logger -n <syslog-remoto>`, p. ej. cada 5 min) y la verificación periódica con `verify-audit --anchor-file`. Sin ancla, el truncado de la cola de la cadena es indetectable.
8. Copias: `docker compose --profile ops run --rm ops backup.sh /backups/x.dump.gpg` (cifrada y firmada; la clave de firma no debería vivir en el mismo servidor). Probar la restauración con `scripts/restore_check.sh` (necesita Python con las dependencias: ejecútalo dentro de la imagen `api` o en un entorno virtual).
9. Monitoreo y alertas (no incluidos): bloqueos de cuenta, accesos de emergencia, fallos de verificación de cadena.

Notas: `proxy/` exige nginx ≥ 1.25.1 (`http2 on;`; la imagen `nginx-unprivileged:1.27` lo cumple). En `/health/ready`, `/docs` y `/openapi.json` el proxy devuelve la página de la SPA (200), no la API; en producción la aplicación además los tiene desactivados.

## Variables de entorno

`APP_ENV` (**obligatoria**; `production` exige `JWT_SECRET` y `AUDIT_HMAC_KEY` ≥ 32, `COOKIE_SECURE=true` y `DATABASE_URL` PostgreSQL), `DATABASE_URL`, `JWT_SECRET`, `AUDIT_HMAC_KEY`, `COOKIE_SECURE`, `SESSION_MINUTES`, `LOGIN_MAX_FAILS`, `LOGIN_LOCK_BASE_MINUTES`, `LOGIN_LOCK_MAX_MINUTES`, `CORS_ORIGINS`, `AUTO_CREATE_TABLES` (solo desarrollo), `TEST_DATABASE_URL`, `TB_ADMIN_PASSWORD`. Cada secreto acepta la variante `NOMBRE_FILE` (ruta a un archivo, como los secretos de Docker) y esta tiene prioridad.

## Estado

| Función | Estado |
|---|---|
| Auth, roles, CSRF, bloqueo con backoff, revocación, cambio obligatorio de contraseña | Implementado y probado (SQLite y PostgreSQL) |
| Pacientes (PII oculta a auditor y admin; acceso de emergencia registrado), evaluación, historial, panel, zona horaria de Bogotá | Implementado y probado |
| Auditoría: dos cadenas HMAC (eventos y accesos), evaluación y contexto ligados al hash, verificador, ancla externa (CLI) | Implementado y probado; **el ancla no está operativa** (falta destino y cron) |
| Mínimo privilegio (`tb_app`, `tb_backup`), triggers append-only, secretos por archivo | Probado contra PostgreSQL 16 local |
| Copia cifrada y firmada, restauración verificada | Probado localmente (GPG, PostgreSQL 16) con datos sintéticos |
| Proxy nginx (cabeceras, límite por IP, sobrescritura de `X-Forwarded-For`) | Probado con nginx 1.24 y TLS autofirmado; **no** con la imagen real ni certificados reales |
| NEWS2 v2.0.0-dev; alertas de embarazo y lesión medular (no cambian el puntaje); bloqueo de menores de 16 | Probado; **pendiente de validación clínica** |
| Docker Compose y las imágenes | **No ejecutado** (no había Docker) |
| CI | Escrito; **no ejecutado** en GitHub Actions |
| FHIR / IA | **No implementado** (adaptador heredado sin conectar) |
| MFA, recuperación de contraseña, cifrado en reposo, monitoreo, relación asistencial (*need-to-know*) | **No implementado** |

Informe completo: `docs/TECHNICAL_REPORT.md`; seguridad: `docs/SECURITY_REVIEW.md`; cumplimiento: `docs/REGULATORY_COMPLIANCE.md`.
