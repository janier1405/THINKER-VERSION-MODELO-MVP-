# Verificación de reglas NEWS2 (estado: PENDIENTE DE VALIDACIÓN CLÍNICA)

Versión implementada: `NEWS2-RCP2017-impl-v2.0.0-dev` (`clinical/algorithms/news2/calculator.py`).
Fuente primaria consultada el 2026-10-26: Royal College of Physicians, *NEWS 2: Executive summary and recommendations*, dic. 2017 (https://www.rcp.ac.uk/media/ctulqqbn/news2-executive-summary_0.pdf), incluidos el texto de las recomendaciones y el texto extraído del gráfico NEWS2.
Fuente secundaria (solo corroboración de SpO₂ escala 2 y oxígeno): protocolo de ensayo clínico NCT04386616, apéndice 4, que reproduce el gráfico.

**Límite de esta verificación:** la hizo un asistente de IA (Claude) leyendo texto extraído de un PDF cuyas columnas llegan desordenadas. Los *rangos* de cada parámetro coinciden con el gráfico; la correspondencia rango→puntaje la contrasté además con las tablas de la fuente secundaria y con las recomendaciones. En la auditoría de código posterior (2026-10-31) se recalculó cada rango contra esta tabla y no se encontraron discrepancias entre el código y lo documentado, pero eso no valida la tabla. **Un profesional debe comparar el código con el gráfico impreso original.** No existe aprobación clínica.

| Componente | Regla implementada | Resultado de la contrastación |
|---|---|---|
| Frecuencia respiratoria | ≤8:3 · 9–11:1 · 12–20:0 · 21–24:2 · ≥25:3 | Rangos coinciden |
| SpO₂ escala 1 | ≤91:3 · 92–93:2 · 94–95:1 · ≥96:0 | Coincide (fuente primaria y secundaria) |
| SpO₂ escala 2 | ≤83:3 · 84–85:2 · 86–87:1 · 88–92:0 · ≥93 en aire:0 · 93–94 con O₂:1 · 95–96 con O₂:2 · ≥97 con O₂:3 | Coincide (fuente primaria y secundaria) |
| Oxígeno suplementario | +2 si requiere oxígeno | Coincide (recomendación 9) |
| Presión sistólica | ≤90:3 · 91–100:2 · 101–110:1 · 111–219:0 · ≥220:3 | Rangos coinciden |
| Frecuencia cardiaca | ≤40:3 · 41–50:1 · 51–90:0 · 91–110:1 · 111–130:2 · ≥131:3 | Rangos coinciden |
| Conciencia (ACVPU) | Alerta:0 · C/V/P/U:3 | Coincide (recomendación 30) |
| Temperatura | ≤35.0:3 · 35.1–36.0:1 · 36.1–38.0:0 · 38.1–39.0:1 · ≥39.1:2 | Rangos coinciden (1 decimal) |
| Bandas | 1–4 bajo · un único 3 · 5–6 medio · ≥7 alto | Coincide con la recomendación 11 |

## Discrepancias potenciales y brechas (para revisión clínica)
1. **Nomenclatura.** La RCP habla de "single red score"; la etiqueta "Bajo-Medio" es una convención de este software, no un término de la fuente.
2. **Puntaje 0 vs 1–4.** La RCP los distingue (frecuencia de monitorización 12 h vs 4–6 h); el software ambos como "Bajo" y no recomienda frecuencias.
3. **Respuesta recomendada.** El texto es genérico ("según protocolo institucional"). No implementa quién responde ni la frecuencia de monitorización (recs. 12, 38–40).
4. **Exclusiones y poblaciones especiales** (actualizado en v0.5):
   - **Menores de 16 años:** bloqueo con código `NEWS2_NOT_APPLICABLE` (rec. 2), registrado en la auditoría (`triage_blocked_age`) y con la ruta `PEDIATRICO_INSTITUCIONAL`. La edad sale de `birth_date` si existe; si no, de la edad registrada, que solo puede sobre-bloquear (la edad nunca decrece). **No existe protocolo pediátrico** (PEWS u otro): el menor queda sin puntaje. Es un cambio de alcance que debe validarse.
   - **Embarazo** (`yes|no|unknown`, obligatorio) **y lesión medular** (obligatorio): **no modifican el puntaje ni los umbrales** (la RCP indica que el gráfico no debe modificarse). Generan alertas (`PREGNANCY_NEWS2_NOT_VALIDATED` y `SPINAL_CORD_INJURY_BASELINE`, nivel duro; `PREGNANCY_UNKNOWN`, nivel blando) que se muestran sobre el puntaje, se guardan con la evaluación y quedan selladas por la huella de auditoría. **Los textos, los niveles y la decisión de avisar en lugar de bloquear en el embarazo son un borrador pendiente de validación clínica.**
5. **Escala 2.** El software guarda el indicador, pero no quién la decidió ni la confirmación de hipercapnia (recs. 25–26). Pendiente de campo de auditoría clínica.
6. **Confusión.** La rec. 31 indica asumir "nueva" si hay duda; la interfaz no lo explica.
7. **Revisión de la fuente.** El documento indica fecha de revisión 2022. No verifiqué si existe una actualización posterior.
8. **Temperatura.** El redondeo a 1 decimal es una decisión de implementación (el gráfico define rangos a 0,1 °C). `round()` de Python usa la representación binaria (p. ej. 36.05 → 36.0): un clínico debe confirmar el tratamiento de los décimos intermedios.
9. La RCP indica que el gráfico y los umbrales **no deben modificarse**; cualquier cambio local debe documentarse y aprobarse.

Pruebas: `tests/test_news2.py` (todos los límites de cada parámetro y bandas), `tests/test_special_populations.py` (edad, bloqueo, alertas que no cambian el puntaje) y `tests/test_security.py::test_news2_age_guard`.
