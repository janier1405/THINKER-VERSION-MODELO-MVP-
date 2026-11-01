# Informe técnico v0.5 — implementado / probado / pendiente

Fecha de verificación: 2026-10-31. Entorno: contenedor Linux (Ubuntu 24.04), Python 3.12.3, Node 22.22.2, PostgreSQL 16 local (instalado con `apt`, puerto 5433), nginx 1.24.0, GnuPG. **No había Docker.** **Solo datos sintéticos. No se desplegó nada.** NEWS2 sigue **PENDIENTE DE VALIDACIÓN CLÍNICA**.

«Verificado» significa ejecutado y observado en ese entorno. El informe v0.4 anterior (2026-10-26) reportó 80 pruebas; esta versión añade las de los bloques de auditoría y corrige defectos hallados al ejecutarlas (§3).

## 1. Suites automatizadas

| # | Verificación | Comando | Resultado |
|---|---|---|---|
| 1 | Backend, SQLite en memoria | `pytest` | **159 aprobadas**, 6 omitidas (exigen PostgreSQL), 0 fallidas |
| 2 | Backend, PostgreSQL 16 real | `TEST_DATABASE_URL=… pytest` | **164 aprobadas**, 1 omitida (`test_deleted_evaluation_is_detected`, solo SQLite: en PostgreSQL la FK impide el borrado), 0 fallidas. Incluye concurrencia de las dos cadenas, fuerza bruta paralela, deadlocks y triggers append-only |
| 3 | Fechas con otra zona horaria de sesión | `PGTZ=Asia/Tokyo` / `America/Bogota` / `UTC` + `pytest tests/test_timezone.py` | 8/8 en cada zona |
| 4 | Frontend: pruebas unitarias | `npm test` (Vitest 5) | 10/10 |
| 5 | Frontend: build de producción | `npm run build` (`tsc` estricto + Vite 7) | OK: JS 161,94 kB (52,06 kB gzip), CSS 4,78 kB |
| 6 | Reproducibilidad de tipos | `npm run gen:api` | Salida idéntica a la versionada |
| 7 | Instalación limpia | `npm ci` desde cero | OK, y luego pasan 4 y 5 |

**Mutaciones** (se quitó cada protección y se comprobó que la prueba correspondiente falla; después se restauró y la suite volvió a pasar):

| Protección eliminada | Prueba que la detectó |
|---|---|
| `FOR UPDATE` en `login` | `test_parallel_bruteforce_cannot_exceed_lockout` |
| `pg_advisory_xact_lock` | `test_both_chains_under_concurrency` |
| `flush()` previo al lock | `test_two_audit_events_in_one_transaction_do_not_collide` |
| `context` dentro de `eval_digest` | `test_removing_alerts_from_the_record_is_detected` |
| PII oculta al `admin` | `test_admin_and_auditor_do_not_see_pii` |
| `session_version` en el cambio de contraseña | `test_new_user_must_change_password_before_anything_else` |
| `FOR UPDATE` en `change_password` | `test_parallel_wrong_current_password_cannot_exceed_lockout` |
| Desfase de Bogotá en `local_day` (PostgreSQL) | `test_dashboard_groups_by_bogota_day` |
| Un `add_header` suelto en un `location` de nginx | `test_security_headers_not_overridden_per_location` |
| Un typo clínico (`spo2_scale2`) o falta de `pregnancy` en el cliente | `tsc` falla en `npm run build` |

## 2. Verificaciones de infraestructura (ejecutadas)

| Verificación | Resultado |
|---|---|
| Migraciones | `upgrade head`, `downgrade -1`, `upgrade head`, `downgrade base`, `upgrade head` sobre PostgreSQL 16: sin errores; los 5 triggers de la 0004 existen |
| `scripts/pg_roles.sql` | Idempotente (dos ejecuciones). Corregido un defecto real (§3). La guarda falla si un rol se eleva y pasa al restaurarlo |
| `scripts/verify_least_privilege.py` con `tb_app` | Flujo de la app OK; 13 operaciones prohibidas denegadas; 3 controles positivos permitidos. Exit 0. Con `GRANT UPDATE ON users` ampliado: marca `PERMITIDO (MAL)` y sale con 1 |
| Copia y restauración (GPG + PostgreSQL 16) | Copia cifrada y firmada con `tb_backup`; el archivo no contiene texto legible; restauración con conteos y **ambas cadenas válidas**. Rechazados: archivo con un byte alterado y `.sha256` regenerado (falla la firma), copia firmada por otro firmante, y BD destino no vacía |
| CLI de ancla | `anchor-audit` genera la ancla; `verify-audit --anchor-file` válido; con el hash de la ancla alterado: exit 1 |
| `scripts/gen_secrets.sh` | Genera 8 secretos (64 caracteres para JWT y HMAC) y se niega a sobrescribir |
| Proxy nginx 1.24 + API real + TLS autofirmado | Cabeceras de seguridad en `/` y `/index.html`; HTTP → 301; TLS 1.0 y 1.1 rechazados, 1.2 y 1.3 aceptados; `X-Forwarded-For` falsificado **no** llega a la auditoría (IP registrada = la real); cuerpo >64 kB → 413; 45 logins rápidos → 5 pasan y el resto 429. `/health/ready`, `/docs` y `/openapi.json` devuelven la SPA (200), no la API |
| Dependencias | Lockfile con 1050 hashes; instalación con `--require-hashes` OK; la app arranca solo con dependencias de producción; `pip-audit`: sin vulnerabilidades; `npm audit`: 0 (tras subir Vite 7 / Vitest 5 y fijar `minimatch` ≥ 11 con un `override`) |
| Compose (YAML) | Ambos archivos parsean; los servicios y secretos están definidos. **No se ejecutaron** |

## 3. Defectos encontrados y corregidos al ejecutar (no al leer)

1. `pg_roles.sql` fallaba en PostgreSQL 16 con un propietario `CREATEROLE` (no superusuario): `ALTER ROLE … NOSUPERUSER` exige ser superusuario. Ahora los roles nacen sin privilegios y el script **verifica** que sigan así.
2. La API devolvía los instantes con el desfase de la sesión de PostgreSQL (`+09:00`) en lugar de UTC. `as_utc` normaliza ahora siempre a UTC.
3. `Dockerfile.proxy` usaba `node:20-alpine`: Vitest 5 exige Node ≥ 22.12 y Node 20 está fuera de soporte. Pasó a Node 22 y se añadió `engines`.
4. Una guarda de `test_infra_files.py` contaba el texto de un comentario como si fuera una directiva.
5. Falsos verdes en mis propias comprobaciones (un respaldo que no se creó, un `sed` que apuntaba a la subclave en vez de a la clave del firmante): se detectaron porque el motivo del fallo no era el esperado, y se rehicieron.
6. Mejoras incluidas de paso: `create_patient` captura la carrera entre dos altas (`IntegrityError` → 409), y `patient_id` de `list_evaluations` tiene `max_length`.

## 4. Implementado (código) y estado de prueba

| Capacidad | Implementado | Verificado |
|---|---|---|
| Auth (argon2id), roles, CSRF, bloqueo con backoff, revocación, cambio obligatorio de contraseña, `unlock` | Sí | Sí (SQLite y PostgreSQL) |
| Minimización por rol, acceso de emergencia, registro de accesos fail-closed | Sí | Sí |
| Auditoría: dos cadenas HMAC, evaluación y contexto ligados al hash, ancla externa (CLI) | Sí | Sí. **El ancla no está operativa** (sin cron ni destino) |
| Mínimo privilegio en BD, triggers append-only, secretos por archivo | Sí | Sí (PostgreSQL 16 local) |
| Copia cifrada y firmada / restauración verificada | Scripts | Sí (local, datos sintéticos) |
| Proxy nginx | Configuración | Sí con nginx 1.24; **no** con la imagen 1.27 ni certificados reales |
| NEWS2 v2.0.0-dev, bloqueo <16 con auditoría, alertas de embarazo y lesión medular | Sí | Unitarias y de API; **sin validación clínica** |
| Zona horaria de Bogotá en panel y filtros; salida siempre en UTC | Sí | Sí (tres zonas de sesión) |
| Frontend: 7 secciones, tipos generados, cambio de contraseña, acceso de emergencia | Sí | Build, Vitest y mutaciones de tipos. **Sin pruebas de componentes; sin revisión manual de accesibilidad** (la v0.4 tuvo axe-core; esta versión no lo repitió) |
| Docker Compose, Dockerfiles | Sí | **No ejecutado** |
| CI (`.github/workflows/ci.yml`) | Sí | **No ejecutado en GitHub** |
| FHIR | Adaptador heredado | **No conectado ni validado** |
| IA/ML | **No existe** | — |

## 5. Privacidad y datos

**Inventario:** nombre, edad, fecha de nacimiento (opcional), sexo e ID del paciente; signos vitales y contexto clínico (embarazo, lesión medular); usuario que evalúa; eventos de auditoría y de acceso (sin nombres; el usuario desconocido en un login se guarda como huella con llave); motivo de los accesos de emergencia (texto libre: no debe contener datos del paciente).

1. *Minimización (parcial):* `auditor` y `admin` sin PII; nombres fuera de URLs y de logs. **Pendiente de decisión del producto:** ¿hace falta almacenar el nombre? La opción más fuerte es solo un identificador seudónimo y mantener el nombre en el sistema clínico de origen.
2. *Cifrado en reposo:* no implementado.
3. *Retención y supresión:* no definidas; la app no borra nada (el rol de mínimo privilegio tampoco puede) y las tablas de evidencia son append-only. Hace falta una política y un procedimiento compatible con la auditoría.
4. *Copias:* cifradas y firmadas por script; sin automatización, retención ni custodia separada de la clave de firma. RPO/RTO no definidos.
5. *Recuperación:* probada en local con un volumen mínimo; falta probarla con volumen real y en la infraestructura destino.

## 6. Pendiente (no verificado ni resuelto)

Ver `REGULATORY_COMPLIANCE.md` §10 y `SECURITY_REVIEW.md` (riesgos residuales). En resumen: base jurídica y capa organizacional de la Ley 1581; validación clínica; ejecución de Docker Compose y del CI; certificados TLS y proxy con la imagen real; ancla externa operativa; MFA y recuperación de contraseña; relación asistencial; cifrado en reposo; monitoreo; SAST/DAST y escaneo de imágenes; pruebas de componentes y de accesibilidad; FHIR e IA (ver `ROADMAP_FHIR_AI.md`).
