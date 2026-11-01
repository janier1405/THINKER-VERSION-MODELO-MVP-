# Revisión de seguridad (v0.5; ver también TECHNICAL_REPORT.md y REGULATORY_COMPLIANCE.md)

**NO es una certificación ni una auditoría independiente.** Es una revisión de ingeniería hecha leyendo el código y ejecutando las pruebas descritas en `TECHNICAL_REPORT.md`, en un entorno Linux con PostgreSQL 16 local y **sin Docker**. «Verificado» significa ejecutado y observado en ese entorno.

## Controles implementados

| Control | Implementación | Verificación |
|---|---|---|
| Configuración segura por defecto | `APP_ENV` obligatorio (`development`/`production`, sin valor por defecto); producción exige `JWT_SECRET` ≥32, `AUDIT_HMAC_KEY` ≥32 bytes, `COOKIE_SECURE=true` y `DATABASE_URL` de PostgreSQL; `/docs` desactivado | `test_security.py`, `test_secrets_and_config.py` |
| Contraseñas | argon2id; mínimo 12 caracteres; no igual a la actual, sin el nombre de usuario, no repetitiva | `test_login`, `test_accounts.py` |
| Contraseña inicial | Los usuarios creados por API quedan con `must_change_password`: solo pueden usar `/me` y `/change-password` hasta cambiarla; el cambio corta las demás sesiones | `test_new_user_must_change_password_before_anything_else` |
| Sesión | JWT en cookie `httpOnly`, `SameSite=Lax`, `Secure` obligatorio en producción, caducidad (60 min por defecto) | `test_login`, `test_headers_*` |
| Revocación | `session_version` por usuario: logout, cambio de contraseña y desactivación invalidan todas las sesiones | `test_logout_revokes_session`, `test_deactivate_*` |
| CSRF | Token aleatorio firmado dentro del JWT + cookie legible + cabecera `X-CSRF-Token` obligatoria en métodos no seguros; comparación en tiempo constante | `test_csrf_*` (incluye token de otra sesión) |
| Fuerza bruta | Bloqueo tras 5 fallos con backoff 1, 2, 4, 8, 16, 30 min; mensaje único; verificación siempre ejecutada; bloqueo de fila (`FOR UPDATE`) para que las peticiones paralelas no lo evadan; el cambio de contraseña comparte el contador | `test_lockout_and_audit`, `test_lock_*`, PostgreSQL: `test_parallel_bruteforce_*`, `test_parallel_wrong_current_*` |
| Deadlocks | Orden de locks fijo: fila de `users` → advisory de auditoría → advisory de accesos | PostgreSQL: `test_login_logout_deactivate_do_not_deadlock` |
| Autorización | Roles verificados en backend; rol leído de la BD en cada petición | `test_roles` |
| Contrato de entrada | `extra="forbid"`, tipos estrictos, `spo2_scale_2`, `pregnancy` y `spinal_cord_injury` obligatorios sin defecto; temperatura solo numérica; `NaN`/`Inf` rechazados | `test_contracts.py` |
| Auditoría | Dos cadenas HMAC-SHA256 (eventos y accesos) con `seq` único, timestamp normalizado a UTC, evaluación (`eval_digest`) y contexto clínico ligados al hash; verificador en streaming; detecta evaluaciones huérfanas | `test_audit_integrity.py`, `test_special_populations.py` |
| Concurrencia de auditoría | `pg_advisory_xact_lock` por cadena; chequeo de `READ COMMITTED` al arrancar; `flush()` previo al lock | PostgreSQL: `test_both_chains_under_concurrency`; mutación sin lock y sin flush detectadas |
| Registro de accesos | Lecturas de pacientes, evaluaciones y panel y accesos de emergencia, registrados **antes** de devolver el dato (fail-closed); la lectura del registro por el auditor también se audita | `test_reads_are_logged_*`, `test_read_fails_closed_*`, `test_break_glass_*` |
| Minimización por rol | `auditor` y `admin` no reciben nombre, edad ni fecha de nacimiento; búsqueda solo por ID; acceso de emergencia (solo `admin`) con motivo de 15–200 caracteres, que lee solo el `auditor` | `test_privacy.py`, `test_accounts.py` |
| Mínimo privilegio en BD | `tb_app`: `SELECT/INSERT` en 5 tablas y `UPDATE` solo en 8 columnas de `users`; `tb_backup` solo lectura; el script verifica que los roles no tengan atributos privilegiados | `scripts/verify_least_privilege.py` contra PostgreSQL 16 (13 operaciones prohibidas denegadas; también falla con exit 1 si se amplía el permiso) |
| Append-only en BD | Triggers que rechazan UPDATE/DELETE/TRUNCATE en `audit_logs`, `access_logs`, `triage_evaluations` | PostgreSQL: `test_append_only_triggers_*`; migración 0004 probada (subir/bajar) |
| Secretos | Variante `NOMBRE_FILE` con prioridad; `gen_secrets.sh` no sobrescribe; nada en imágenes ni en el compose | `test_secrets_and_config.py`, `test_infra_files.py`; `gen_secrets.sh` ejecutado |
| Cabeceras y errores | nosniff, X-Frame-Options, no-referrer, `no-store` en `/api`; error 500 genérico sin datos clínicos; `/health/ready` sin detalles | `test_headers_*`, `test_ready_*` |
| Proxy | TLS 1.2/1.3 (1.0/1.1 rechazados), HSTS, CSP, límite por IP (login 30/min), cuerpo ≤64 kB, `X-Forwarded-For` sobrescrito | Probado con nginx 1.24 real y TLS autofirmado (ver `TECHNICAL_REPORT.md` §2) |
| Copias | `backup.sh` cifrado y firmado con GPG y rol `tb_backup`; `restore_check.sh` exige BD vacía, firma del firmante esperado y ambas cadenas válidas | Ciclo real: acepta la copia legítima; rechaza byte alterado (incluso con `.sha256` regenerado), firmante distinto y BD no vacía |
| Cadena de suministro | Lockfile con 1050 hashes y `--require-hashes`; producción sin herramientas de prueba; `npm ci` con lockfile | Instalación con hashes ejecutada; `pip-audit`: sin vulnerabilidades; `npm audit`: 0 |
| Cliente web | Tipos generados desde OpenAPI (un typo clínico no compila); cancelación de peticiones obsoletas; 401 devuelve al login; formulario limpio tras guardar; `admin` ve datos de emergencia solo en memoria | Vitest (10), `tsc` estricto con mutaciones; **sin pruebas de componentes** |

## Riesgos residuales (aceptados o pendientes)

1. **`INSERT` sobre `users` para `tb_app`.** Una inyección SQL podría crear un usuario admin; no se cierra con permisos porque el alta por API lo exige. Detección sugerida: verificar que cada usuario tenga su evento `user_created`, salvo el admin del CLI.
2. **`UPDATE (password_hash)` para `tb_app`.** Necesario para el cambio de contraseña; una función `SECURITY DEFINER` no lo mejora (la misma inyección podría invocarla).
3. **El propietario de la BD y quien tenga `AUDIT_HMAC_KEY`** pueden falsificar la cadena o desactivar triggers. Mitigación: ancla externa y custodia separada de la clave.
4. **Truncado de la cola de la cadena:** indetectable sin ancla externa. El CLI existe y está probado; **falta el cron y el destino WORM**.
5. **Pérdida de `AUDIT_HMAC_KEY`:** la cadena deja de ser verificable. Sin rotación: falta `key_id`; cambiar la función de hash invalida la cadena existente (falta `hash_version`).
6. **Sin MFA, sin recuperación de contraseña, sin lista de claves filtradas ni historial.**
7. **`failed_attempts` no decae con el tiempo:** cuatro fallos antiguos más un error de tipeo bloquean a un usuario legítimo. En urgencias es un riesgo asistencial; el backoff y el `unlock` de admin lo mitigan, pero hay denegación de servicio dirigida a una cuenta conocida.
8. **Fuga por tiempo:** un usuario inexistente genera un evento de auditoría y uno bloqueado no; la latencia podría delatar una cuenta bloqueada. La cadena crece con cada intento con usuario desconocido (acotado por el límite del proxy).
9. **Sin timeout por inactividad ni sesión por dispositivo.**
10. **Todo clínico lee a todo paciente** (falta modelar la relación asistencial). El acceso de emergencia no genera alertas: solo registro.
11. **Sin cifrado en reposo** (depende de la infraestructura) ni del volcado en el servidor más allá de GPG; **sin retención ni supresión definidas.**
12. **`--forwarded-allow-ips "*"` en uvicorn** es seguro solo mientras la API no sea alcanzable salvo desde el proxy (red `internal` del compose).
13. **Sin SAST/DAST ni escaneo de imágenes;** `pip-audit` y `npm audit` verifican solo avisos conocidos de dependencias. Las imágenes base están por *tag*, no por *digest*.
14. **Sin monitoreo ni alertas** (bloqueos, accesos de emergencia, fallos de verificación, `login_unknown_user` en ráfaga).
15. **Sin revisión legal** (Ley 1581 de 2012 y normas de historia clínica e interoperabilidad) ni evaluación de si aplica regulación de dispositivos médicos: ver `REGULATORY_COMPLIANCE.md`.
16. **Idempotencia:** `evaluate` no tiene clave de idempotencia; un reintento por red caída duplica la evaluación.
17. **Cookies:** sin prefijo `__Host-`, `SameSite=Lax` (podría ser `Strict`), `delete_cookie` sin los mismos atributos que `set_cookie`.
