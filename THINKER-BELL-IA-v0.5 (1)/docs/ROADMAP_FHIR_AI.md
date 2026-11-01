# Estado real y hoja de ruta: FHIR e IA

## Estado real
**FHIR:** existe `interoperability/fhir/resources/fhir_adapter.py` heredado de v0.1. **No es una integración funcional.** No está conectado a ningún endpoint, no se adaptó al esquema v2 (su import está neutralizado con `TriageRequestSchema = object`), no se validó contra ningún validador FHIR y no tiene pruebas. Problemas conocidos: `birthDate: null` es JSON inválido; `effectiveDateTime` usa la hora actual; exporta `name` (PII) sin una política que lo justifique; el Bundle es de tipo `collection` (no idempotente) y no incluye el Patient ni un Encounter; no mapea conciencia, oxígeno ni el puntaje; el código LOINC de SpO₂ está por verificar (el borrador de Gemini usaba `75622-1` para NEWS2, que no se ha podido confirmar: verificar cada código en loinc.org).
**IA/ML:** **no existe ningún modelo**, dato de entrenamiento, métrica ni código de inferencia. La interfaz muestra únicamente el puntaje NEWS2. No debe afirmarse ninguna capacidad de IA ni cifras de precisión.

## Hoja de ruta FHIR (propuesta, requiere decisiones del producto; bloqueada por la base jurídica y la validación clínica)
1. Definir casos de uso y el sistema externo concreto (HIS/HCE, versión FHIR, perfiles; para Colombia, revisar la normativa de interoperabilidad vigente).
2. Reescribir el adaptador sobre el esquema v2 con `fhir.resources` o equivalente: Patient + Encounter + Observation (perfil Vital Signs) + Provenance (clínico, `algorithm_version`, `rules_status`); IDs deterministas (`uuid5` del `evaluation_id`); Bundle `transaction` con `PUT` o `ifNoneExist`; `effectiveDateTime` igual al de la evaluación; solo el seudónimo, sin `name`, salvo acuerdo explícito.
3. Validar con el validador oficial de HL7 y casos sintéticos; añadir pruebas.
4. Arquitectura: el motor clínico **nunca** llama a la HCE de forma síncrona.

```
evaluate() ──(misma transacción)──► triage_evaluations + audit_logs + fhir_outbox(pending)
                                                          │
          worker aparte (FOR UPDATE SKIP LOCKED) ──► CircuitBreaker ──► FhirClient (mTLS / SMART backend services)
```

   - Circuit breaker (cerrado → abierto tras N fallos reintentables → semiabierto tras un tiempo) y reintentos con *backoff* exponencial con jitter completo; los errores 4xx de validación van a `dead` sin reintento.
   - `fhir_outbox`: `evaluation_id` único, `status` (`pending|sent|dead`), `attempts`, `next_attempt_at`, `last_error` (solo un código, nunca el cuerpo: puede contener PHI). No duplica PHI: el Bundle se construye al enviar a partir de la evaluación inmutable.
   - Rol de BD propio para el worker con `UPDATE` solo sobre `fhir_outbox`; cada exportación genera un evento `fhir_export` en la cadena de auditoría.
   - Alerta de monitoreo cuando `dead > 0` o haya `pending` con antigüedad mayor que el RPO.
5. Endpoint de exportación de solo lectura, con roles y auditoría; luego importación, con idempotencia y conciliación de identificadores.
6. Seguridad: OAuth2/SMART on FHIR o mTLS, acuerdos de acceso, cifrado, registro de accesos.
7. Pruebas de integración en un entorno de pruebas del tercero.

## Hoja de ruta IA (propuesta; nada de esto está iniciado)
1. Definir la pregunta clínica, la población y el uso previsto, y si aplica regulación de software como dispositivo médico.
2. Gobernanza de datos: base legal, autorización, anonimización, comité de ética; **sin datos clínicos reales hasta tenerla**.
3. Diseño experimental: partición temporal/por paciente (evitar fuga), línea base NEWS2, métricas de discriminación y calibración, análisis de sesgo por subgrupos.
4. Entrenamiento reproducible separado de la inferencia; versionado de datos, código y modelo; ficha del modelo.
5. Validación externa y prospectiva en modo sombra; revisión clínica antes de mostrar nada al usuario.
6. Monitoreo de deriva y plan de retirada. La IA solo complementaría, nunca sustituiría, la evaluación profesional.
