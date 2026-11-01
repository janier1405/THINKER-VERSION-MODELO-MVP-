"""Alertas por población especial. NO alteran el puntaje NEWS2 (la RCP indica que el gráfico no debe modificarse).
ESTADO: PENDIENTE DE VALIDACIÓN CLÍNICA: textos y niveles requieren revisión de un profesional."""
from typing import Literal

ALERTS_VERSION = "ALERTS-impl-v1.0.0-dev"
PEDIATRIC_ROUTE = "PEDIATRICO_INSTITUCIONAL"
Pregnancy = Literal["yes", "no", "unknown"]

_PREGNANCY_YES = {"code": "PREGNANCY_NEWS2_NOT_VALIDATED", "severity": "hard",
    "text": "Embarazo: NEWS2 no está validado en gestantes (RCP 2017, verificar rec. 2). El puntaje es orientativo. "
            "Aplica el protocolo obstétrico institucional y decide con criterio clínico."}
_PREGNANCY_UNKNOWN = {"code": "PREGNANCY_UNKNOWN", "severity": "soft",
    "text": "Estado de embarazo no determinado. Confírmalo antes de interpretar el puntaje."}
_SCI = {"code": "SPINAL_CORD_INJURY_BASELINE", "severity": "hard",
    "text": "Lesión medular: los signos vitales basales pueden diferir de la población de referencia por alteración autonómica. "
            "Interpreta el puntaje con criterio clínico y escala ante cualquier duda."}

def build_alerts(pregnancy: Pregnancy, spinal_cord_injury: bool) -> list[dict]:
    out: list[dict] = []
    if pregnancy == "yes": out.append(dict(_PREGNANCY_YES))
    elif pregnancy == "unknown": out.append(dict(_PREGNANCY_UNKNOWN))
    if spinal_cord_injury: out.append(dict(_SCI))
    return out
