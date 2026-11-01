# Matriz de trazabilidad regulatoria y cumplimiento — Thinker Bell

*Estado del repositorio v0.5 · 31-oct-2026 · Documento de ingeniería: no es una certificación, una auditoría independiente ni un concepto jurídico.*

## 1. Cómo leer este documento

Describe **lo que el repositorio hace hoy**, no lo que se quiere que haga. Reemplaza la matriz de los borradores previos (generados con Gemini), que afirmaba capacidades inexistentes (hallazgo C-1).

**Estado del requisito**

- ✅ **Implementado**: existe código y pruebas que lo ejercitan.
- 🟡 **Parcial**: existe una parte; la brecha está indicada.
- ❌ **No implementado**: no existe en el repositorio.

**Verificación** (columna *Verif.*)

- **V**: ejecutado y observado en el entorno de auditoría (Linux, Python 3.12, PostgreSQL 16 local, nginx 1.24, Node 22; resultados en `TECHNICAL_REPORT.md`).
- **N**: escrito pero **no ejecutado** (requiere Docker, certificados reales, GitHub Actions u operación real).
- **—**: no aplica o no existe.

**Referencias legales.** Las citas de artículos y resoluciones son orientativas y deben ser confirmadas por asesoría jurídica antes de presentar este documento a un ente de control. Algunas citas de los borradores previos eran incorrectas (ver §8).

## 2. Resumen ejecutivo

| Estado | Filas |
|---|---|
| ✅ Implementado | 11 |
| 🟡 Parcial | 19 |
| ❌ No implementado | 21 |
| **Total** | **51** |

**Lo que es sólido.** Autenticación y sesión endurecidas, control de acceso por rol en el servidor, contrato de entrada estricto, evidencia de auditoría con detección de manipulación (HMAC, evaluación y contexto ligados al hash, registro de lecturas), mínimo privilegio en la base de datos con triggers append-only, copias cifradas y firmadas con restauración verificada, dependencias fijadas con hashes y sin avisos conocidos.

**Lo que impide usar datos reales hoy (bloqueantes):**

1. **Base jurídica del tratamiento de datos de salud.** No hay política de tratamiento, autorización, revocatoria, canal de titulares, registro de bases de datos ni procedimiento de incidentes (§3).
2. **Validación clínica.** NEWS2 sigue *pendiente de validación clínica*; los textos de alertas, la ruta pediátrica y la respuesta por banda no están aprobados (§6).
3. **Verificación operativa.** Docker Compose, las imágenes, el proxy con certificados reales y el CI no se han ejecutado. Tampoco hay MFA, cifrado en reposo, ancla externa operativa ni monitoreo (§7).

**Lo que este sistema no es.** No es una historia clínica electrónica, no tiene firma digital, no tiene IA, no tiene integración FHIR funcional y no es un dispositivo médico autorizado.

## 3. Ley 1581 de 2012 (protección de datos personales) y reglamentarios

| ID | Requisito | Módulo / evidencia | Estado | Verif. | Brecha |
|---|---|---|---|---|---|
| L-01 | Seguridad de la información (Art. 4 lit. g; deberes del responsable, Art. 17) | argon2id, CSRF, bloqueo con backoff, RBAC, cabeceras, secretos por archivo, mínimo privilegio en BD (`core/security.py`, `auth.py`, `pg_roles.sql`) | 🟡 | V | Sin MFA, sin cifrado en reposo, sin SAST/DAST, despliegue no verificado |
| L-02 | Acceso y circulación restringida; confidencialidad (Art. 4 lit. f, h) | RBAC en servidor; PII oculta a `auditor` y `admin`; acceso de emergencia con motivo y registro (`patients.py`; `test_accounts.py`) | 🟡 | V | Todo clínico lee a todo paciente: falta relación asistencial (*need-to-know*) |
| L-03 | Trazabilidad de quién consulta o modifica datos | Cadena `access_logs` con HMAC, registro previo a la respuesta (fail-closed), `/audit/access-logs` solo para auditor (`test_audit_integrity.py`) | ✅ | V | Sin alertas en tiempo real ni pantalla de revisión; el lock global puede ser cuello de botella con carga alta |
| L-04 | Finalidad y minimización (Art. 4 lit. b) | ID seudónimo; búsqueda solo por ID; `birth_date` opcional; nombre, edad y fecha ocultos a auditor y admin | 🟡 | V | El nombre se guarda en claro; decisión de producto pendiente de si es necesario |
| L-05 | Datos sensibles de salud: tratamiento reforzado (Arts. 5 y 6) | Ninguno: el sistema no distingue bases de tratamiento | ❌ | — | Definir y registrar la base de tratamiento |
| L-06 | Excepción de autorización por urgencia médica o sanitaria (Art. 10, ver §8) | Ninguno: no hay campo de base jurídica ni módulo de urgencia vital | ❌ | — | Requiere criterio jurídico sobre cuándo aplica y cómo se documenta |
| L-07 | Autorización previa, expresa e informada y prueba de ella (Art. 9) | Ninguno: no existe tabla ni endpoints de consentimiento | ❌ | — | El módulo de los borradores de Gemini no está en el repositorio |
| L-08 | Revocatoria de la autorización y supresión (Art. 8) | Ninguno | ❌ | — | Choca con tablas append-only: requiere diseño de supresión o anonimización compatible con la auditoría |
| L-09 | Consulta, actualización y rectificación por el titular (Arts. 8, 14, 15) | Ninguno: no hay `PATCH /patients` ni canal de titulares | ❌ | — | Rectificar exige evento de auditoría y regla de quién puede hacerlo |
| L-10 | Política de tratamiento y aviso de privacidad (Art. 17; Decreto 1377/2013, compilado en el Decreto 1074/2015) | Ninguno | ❌ | — | Documento organizacional |
| L-11 | Registro Nacional de Bases de Datos (Art. 25) | Ninguno | ❌ | — | Trámite del responsable ante la SIC |
| L-12 | Gestión y reporte de incidentes de seguridad | Ninguno: sin detección, alertas ni procedimiento | ❌ | — | Definir procedimiento y vía de reporte a la SIC |
| L-13 | Responsable y encargado, contratos de transmisión, hosting y transferencias internacionales (Arts. 17, 18, 26) | Ninguno | ❌ | — | Depende de la decisión de infraestructura |
| L-14 | Retención y supresión al vencimiento de la finalidad | Ninguno: la aplicación no borra nada y su rol de BD tampoco puede | ❌ | — | Política de retención compatible con L-08 y con H-03 |

## 4. Ley 527 de 1999 (mensajes de datos y firmas)

| ID | Requisito | Módulo / evidencia | Estado | Verif. | Brecha |
|---|---|---|---|---|---|
| S-01 | Integridad de los registros | Cadena de auditoría HMAC-SHA256 con timestamp, evaluación (`eval_digest`) y contexto clínico ligados al hash; verificación en streaming (`services/audit.py`) | 🟡 | V | Es evidencia de integridad **interna**: la clave simétrica la custodia el operador. No es firma digital ni da no repudio frente a terceros |
| S-02 | Firma digital o electrónica del triaje por el profesional responsable | Ninguno | ❌ | — | El módulo de los borradores firmaba con una clave del servidor, que no identifica al profesional. Requiere decidir el tipo de firma y la identidad del firmante |
| S-03 | Anclaje externo y sellado de tiempo | CLI `anchor-audit` y `verify-audit` con ancla; prueba de truncado de cola; ancla alterada rechazada | 🟡 | V | Sin cron ni destino WORM; sin sellado de tiempo de un tercero. Sin ancla, el truncado de cola es indetectable |
| S-04 | Conservación de mensajes de datos | Ninguno | ❌ | — | Retención no definida; copias sin automatizar |

## 5. Historia clínica e interoperabilidad

| ID | Requisito | Módulo / evidencia | Estado | Verif. | Brecha |
|---|---|---|---|---|---|
| H-01 | Identificación del autor y fecha de cada registro (Res. 1995/1999) | `clinician_id` y timestamp UTC en cada evaluación; la API siempre devuelve UTC y la interfaz muestra hora de Bogotá (`timeutil.py`, `test_timezone.py`) | ✅ | V | Falta determinar si estos registros forman parte de la historia clínica institucional |
| H-02 | No alteración posterior de lo registrado | Sin UPDATE/DELETE para `tb_app`, triggers append-only, detección por HMAC | 🟡 | V | El propietario de la BD puede desactivar triggers; solo el ancla externo lo haría visible |
| H-03 | Custodia y tiempos de conservación (Res. 1995/1999 y 839/2017) | Ninguno | ❌ | — | Política de retención y custodia |
| H-04 | Interoperabilidad con la HCE (Ley 2015/2020) y FHIR R4 | `fhir_adapter.py` heredado, **sin conectar** y no validado; solo hoja de ruta (`ROADMAP_FHIR_AI.md`) | ❌ | — | Rediseño con outbox, worker y circuit breaker; bloqueado por base jurídica y validación clínica |
| H-05 | Software como dispositivo médico (INVIMA; Decreto 4725/2005, verificar) | Ninguno: la aplicación se declara «no dispositivo médico» | ❌ | — | Evaluación regulatoria pendiente |

## 6. Motor clínico y gobernanza de IA

| ID | Requisito | Módulo / evidencia | Estado | Verif. | Brecha |
|---|---|---|---|---|---|
| C-01 | NEWS2 conforme a la RCP 2017 | `calculator.py`; pruebas de todos los límites (`test_news2.py`); `NEWS2_VERIFICATION.md` | 🟡 | V | Estado `PENDIENTE_DE_VALIDACION_CLINICA`; la verificación la hizo un asistente de IA y debe confirmarla un profesional contra el gráfico impreso |
| C-02 | Menores de 16 años | Bloqueo 422 con código `NEWS2_NOT_APPLICABLE`, evento `triage_blocked_age`, ruta etiquetada `PEDIATRICO_INSTITUCIONAL`; edad por `birth_date` (`test_special_populations.py`) | 🟡 | V | No existe protocolo pediátrico (PEWS u otro). Contradice «cero exclusiones»: el menor queda sin puntaje |
| C-03 | Embarazo y lesión medular | Alertas que **no alteran el puntaje**, guardadas y selladas en el hash | 🟡 | V | Textos y niveles son borrador y requieren validación clínica |
| C-04 | Rol de respuesta y frecuencia de monitorización por banda (RCP recs. 12 y 38–40) | Ninguno: la respuesta es genérica («según protocolo institucional») | ❌ | — | Decisión clínica |
| C-05 | Reproducibilidad de cada evaluación | Versión del algoritmo, vitales, contexto y huella guardados por evaluación | ✅ | V | — |
| C-06 | Explicabilidad | Desglose de puntaje por parámetro en pantalla | 🟡 | V | Es un cálculo determinista, no IA; sin explicación de la banda más allá de la tabla |
| C-07 | Humano en el circuito | La aplicación no decide; el resultado es apoyo y lo emite un clínico | 🟡 | V | No se registra la validación o aceptación del resultado por el profesional |
| C-08 | IA/ML | **No existe** ningún modelo, dato de entrenamiento ni inferencia | ❌ | — | No afirmar capacidades ni cifras de precisión |

## 7. Controles técnicos

Referencia orientativa: temas del Anexo A de ISO/IEC 27001. ISO 27001 certifica una organización, no un software; HIPAA es normativa estadounidense y no aplica directamente.

| ID | Control | Módulo / evidencia | Estado | Verif. | Brecha |
|---|---|---|---|---|---|
| T-01 | Contraseñas | argon2id; mínimo 12; reglas básicas; bloqueo con backoff 1–30 min; `unlock` de admin; cambio obligatorio en el primer ingreso (`auth.py`, `test_accounts.py`) | ✅ | V | Sin lista de claves filtradas ni historial |
| T-02 | MFA y recuperación de contraseña | Ninguno | ❌ | — | Sin MFA; si alguien olvida su clave, nadie puede restablecerla |
| T-03 | Sesión | JWT en cookie `httpOnly`, `SameSite=Lax`, `Secure` obligatorio en producción, caducidad, revocación por `session_version` | 🟡 | V | Sin timeout por inactividad ni sesión por dispositivo; sin prefijo `__Host-` |
| T-04 | CSRF | Token ligado a la sesión, cabecera obligatoria en métodos no seguros | ✅ | V | — |
| T-05 | Autorización | Roles en el servidor, leídos de la BD en cada petición (`require_roles`) | ✅ | V | — |
| T-06 | Validación de entrada | `extra="forbid"`, tipos estrictos, contexto clínico obligatorio sin defectos (`test_contracts.py`); tipos generados en el cliente | ✅ | V | — |
| T-07 | Auditoría con detección de manipulación | Dos cadenas HMAC, `pg_advisory_xact_lock`, verificación de evaluaciones huérfanas; 8 mutaciones de protección detectadas por las pruebas | 🟡 | V | Ver S-03; sin rotación de clave (`key_id`) ni `hash_version` |
| T-08 | Mínimo privilegio en BD | `tb_app` con `UPDATE` por columna, triggers append-only, `verify_least_privilege.py` con salida distinta de cero | ✅ | V | Riesgos residuales en `SECURITY_REVIEW.md` |
| T-09 | Gestión de secretos | Lectura `*_FILE`, `gen_secrets.sh`, nada en la imagen ni en el compose | ✅ | V | Sin rotación de la clave HMAC; la custodia de la clave fuera del servidor es manual |
| T-10 | Configuración segura por defecto | `APP_ENV` obligatorio, producción exige secretos y `COOKIE_SECURE`, `/docs` apagado | ✅ | V | — |
| T-11 | Transporte y perímetro | `proxy/` con TLS 1.2/1.3, HSTS, CSP, límite por IP, `X-Forwarded-For` sobrescrito | 🟡 | V/N | Probado con nginx 1.24 y TLS autofirmado; **no** con la imagen 1.27 (`http2 on`) ni certificados reales; renovación pendiente |
| T-12 | Cifrado en reposo | Ninguno | ❌ | — | Depende de la infraestructura (disco o BD gestionada) |
| T-13 | Copias y restauración | Cifrado y firma GPG, rol `tb_backup`, `restore_check.sh` con verificación de firma y de cadenas; ciclo real con rechazos | 🟡 | V | Sin automatización, retención, RPO/RTO ni custodia separada de la clave de firma |
| T-14 | Dependencias | Lockfile con 1050 hashes instalado con `--require-hashes`; producción sin herramientas de prueba; `npm ci` | ✅ | V | Las imágenes base siguen por *tag*, no por *digest* |
| T-15 | Escaneo de vulnerabilidades | `pip-audit` y `npm audit` ejecutados (sin avisos) | 🟡 | V | Sin SAST/DAST ni escaneo de imágenes |
| T-16 | CI/CD | `.github/workflows/ci.yml` con los mismos comandos ejecutados a mano | 🟡 | N | No ejecutado en GitHub Actions |
| T-17 | Alta disponibilidad, incidentes de masa, RPO/RTO | Instancia única; sin pruebas de carga | ❌ | — | No afirmar RPO < 1 min ni RTO < 15 min |
| T-18 | Contenedores y salud | Dockerfiles multi-etapa no root, `read_only`, `cap_drop`, `HEALTHCHECK`; `/health/ready` | 🟡 | V/N | `/health/ready` probado; **Docker y el compose no se ejecutaron** |
| T-19 | Monitoreo y alertas | Ninguno | ❌ | — | Alertas de acceso de emergencia, bloqueos y fallos de verificación |
| T-20 | Cliente web | Tipos generados desde OpenAPI, cancelación de peticiones, manejo de 401, limpieza de formulario; Vitest y `tsc` estricto | 🟡 | V | Sin pruebas de componentes ni auditoría manual de accesibilidad |

## 8. Afirmaciones que no deben hacerse

Los borradores previos contenían estas afirmaciones. Presentarlas a un ente de control sería inexacto.

| Afirmación en los borradores | Realidad |
|---|---|
| MFA con TOTP y *rate limiting* en `core/security.py` | No hay MFA. El límite por IP está en la configuración del proxy, aún no desplegada |
| Firma digital por evaluación (Ley 527) | No existe. Ver S-02 |
| «Inmutable» / *blockchain-style* | Es una cadena HMAC con detección de manipulación; el truncado de cola solo se detecta con ancla externa |
| TLS 1.3 exclusivo | La configuración admite TLS 1.2 y 1.3 para no excluir equipos hospitalarios antiguos |
| PEWS pediátrico | No existe. El borrador puntuaba solo la frecuencia cardiaca con cortes fijos: clínicamente inválido |
| RBAC del borrador | Aceptaba cualquier cadena como usuario válido (bypass total). No se portó |
| Módulo de consentimiento y revocatoria | No existe. Ver L-07 y L-08 |
| Excepción de urgencia «Art. 10 lit. b» | A mi entender el literal de urgencia médica es el **c**; el b corresponde a datos de naturaleza pública. Confirmar con asesoría |
| «Resolución 823 de 2017» | A mi entender la norma que modifica la Res. 1995/1999 es la **839 de 2017**. Confirmar |
| FHIR bidireccional, XAI | Adaptador sin conectar; no hay IA |
| RPO < 1 min, RTO < 15 min | No definidos ni probados |
| «Cumple a cabalidad con la normativa» | Falta toda la capa organizacional y jurídica (§3) |
| Contraseñas de ejemplo (`SecureClinicalPassword2026!`, `SuperSecureClientSecretFhir2026!`) | Si llegaron a algún `.env`, CI o compose, considérelas comprometidas |

## 9. Riesgos residuales

Listados y numerados en `SECURITY_REVIEW.md` (sección «Riesgos residuales»).

## 10. Plan para cerrar las brechas (por prioridad)

| # | Acción | Cierra | Responsable |
|---|---|---|---|
| 1 | Revisión jurídica: base de tratamiento, política, aviso, autorización, RNBD, incidentes, roles de responsable y encargado | L-05 a L-13 | Legal / DPO |
| 2 | Validación clínica de NEWS2, textos de alertas, ruta pediátrica, rol y frecuencia por banda | C-01 a C-04 | Clínico |
| 3 | Ejecutar `docker compose up --build` en un entorno de pruebas y el CI en GitHub; verificar el proxy con la imagen 1.27 y certificados reales | T-11, T-16, T-18 | Infraestructura |
| 4 | Ancla externa operativa (cron y destino WORM) y custodia de la clave HMAC | S-03, T-07, T-09 | Infraestructura / Seguridad |
| 5 | Fijar imágenes por *digest*; SAST y escaneo de imágenes | T-14, T-15 | Ingeniería |
| 6 | MFA, recuperación de contraseña, timeout por inactividad | T-02, T-03 | Ingeniería |
| 7 | Relación asistencial (*need-to-know*), alertas y pantalla de revisión de accesos | L-02, L-03, T-19 | Producto / Ingeniería |
| 8 | Política de retención, supresión y rectificación compatibles con la auditoría | L-08, L-09, L-14, H-03, S-04 | Legal / Producto |
| 9 | Cifrado en reposo, copias automatizadas, RPO/RTO y pruebas de carga | T-12, T-13, T-17 | Infraestructura |
| 10 | Decisión sobre firma del profesional y evaluación como dispositivo médico | S-02, H-05 | Legal / Producto |
| 11 | FHIR (outbox, worker, circuit breaker) solo después de 1 y 2 | H-04 | Ingeniería |
| 12 | Pendientes de menor prioridad: autoría de la escala 2, `CHECK` en `users.role` y `clinical_risk`, idempotencia de `evaluate`, `__Host-` y `SameSite=Strict`, pruebas de componentes | C-01, T-03, T-20 | Ingeniería |

## 11. Preguntas abiertas para asesoría

**Jurídicas**

- ¿Qué registros de la aplicación forman parte de la historia clínica y por cuánto tiempo deben conservarse?
- ¿Cómo se documenta la excepción de urgencia y cómo se compagina la supresión con tablas append-only?
- ¿Qué tipo de firma exige la institución para el triaje?
- ¿Aplica regulación de software como dispositivo médico?

**Clínicas**

- ¿El embarazo avisa o bloquea? Hoy avisa con alerta dura.
- ¿Qué protocolo pediátrico usa la institución?
- ¿Quién responde y con qué frecuencia se monitoriza en cada banda?
- ¿Qué diferencia debe verse entre el puntaje 0 y el de 1 a 4?

## 12. Mantenimiento de la matriz

- Cada fila ✅ o 🟡 cita su evidencia (archivo o prueba). Si la prueba se borra o cambia, la fila baja de estado.
- Regenerar la matriz en cada versión y registrar la fecha de la última ejecución completa de las suites y quién la hizo.
- Un ente de control debería recibir este documento junto con la salida de las pruebas, no en lugar de ella.
- Mantener coherentes `README.md`, `SECURITY_REVIEW.md`, `TECHNICAL_REPORT.md` y `NEWS2_VERIFICATION.md` con esta matriz.
