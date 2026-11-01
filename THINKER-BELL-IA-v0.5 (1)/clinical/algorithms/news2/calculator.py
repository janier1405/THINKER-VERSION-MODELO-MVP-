"""Motor NEWS2 determinístico. ESTADO: PENDIENTE DE VALIDACIÓN CLÍNICA.

Fuente de referencia: Royal College of Physicians, National Early Warning Score (NEWS) 2, 2017.
Cambios frente a v1.1.0-dev (cada uno requiere confirmación clínica):
 - Añade oxígeno suplementario (+2 puntos).
 - SpO2 escala 2: valores >=93 solo puntúan con oxígeno suplementario; en aire ambiente puntúan 0.
 - Bandas: total 0-4 bajo; un único parámetro en 3 -> bajo-medio; 5-6 medio; >=7 alto.
 - Temperatura se redondea a 1 decimal (los rangos oficiales se definen a 0,1 °C).
No es diagnóstico ni sustituye el protocolo institucional ni el juicio profesional.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict

ALGORITHM_VERSION = "NEWS2-RCP2017-impl-v2.0.0-dev"
RULES_STATUS = "PENDIENTE_DE_VALIDACION_CLINICA"
RULES_SOURCE = "Royal College of Physicians. National Early Warning Score (NEWS) 2. 2017."

class ConsciousnessLevel(str, Enum):
    ALERT = "A"; NEW_CONFUSION = "C"; VERBAL = "V"; PAIN = "P"; UNRESPONSIVE = "U"

@dataclass(frozen=True)
class VitalSigns:
    respiratory_rate: int
    oxygen_saturation: int
    supplemental_oxygen: bool
    spo2_scale_2: bool          # escala 2: la indica un profesional autorizado
    systolic_bp: int
    heart_rate: int
    consciousness: ConsciousnessLevel
    temperature: float

@dataclass(frozen=True)
class NEWS2Result:
    total_score: int
    parameter_scores: Dict[str, int]
    clinical_risk: str
    recommended_response: str
    algorithm_version: str
    rules_status: str

class NEWS2Calculator:
    @staticmethod
    def _score_respiratory_rate(rr: int) -> int:
        if rr <= 8 or rr >= 25: return 3
        if rr >= 21: return 2
        if rr >= 12: return 0
        return 1

    @staticmethod
    def _score_oxygen_sat(spo2: int, scale_2: bool, on_oxygen: bool) -> int:
        if not scale_2:
            return 3 if spo2 <= 91 else 2 if spo2 <= 93 else 1 if spo2 <= 95 else 0
        if spo2 <= 83: return 3
        if spo2 <= 85: return 2
        if spo2 <= 87: return 1
        if spo2 <= 92 or not on_oxygen: return 0
        return 1 if spo2 <= 94 else 2 if spo2 <= 96 else 3

    @staticmethod
    def _score_supplemental_oxygen(on_oxygen: bool) -> int:
        return 2 if on_oxygen else 0

    @staticmethod
    def _score_systolic_bp(sbp: int) -> int:
        if sbp <= 90 or sbp >= 220: return 3
        return 2 if sbp <= 100 else 1 if sbp <= 110 else 0

    @staticmethod
    def _score_heart_rate(hr: int) -> int:
        if hr <= 40 or hr >= 131: return 3
        if hr >= 111: return 2
        return 1 if (hr <= 50 or hr >= 91) else 0

    @staticmethod
    def _score_consciousness(c: ConsciousnessLevel) -> int:
        return 0 if c == ConsciousnessLevel.ALERT else 3

    @staticmethod
    def _score_temperature(temp: float) -> int:
        t = round(temp, 1)
        if t <= 35.0: return 3
        if t <= 36.0: return 1
        if t <= 38.0: return 0
        return 1 if t <= 39.0 else 2

    @classmethod
    def evaluate(cls, v: VitalSigns) -> NEWS2Result:
        s = {
            "respiratory_rate": cls._score_respiratory_rate(v.respiratory_rate),
            "oxygen_saturation": cls._score_oxygen_sat(v.oxygen_saturation, v.spo2_scale_2, v.supplemental_oxygen),
            "supplemental_oxygen": cls._score_supplemental_oxygen(v.supplemental_oxygen),
            "systolic_bp": cls._score_systolic_bp(v.systolic_bp),
            "heart_rate": cls._score_heart_rate(v.heart_rate),
            "consciousness": cls._score_consciousness(v.consciousness),
            "temperature": cls._score_temperature(v.temperature),
        }
        total = sum(s.values())
        if total >= 7:
            risk, resp = "Alto", "Respuesta de emergencia: valoración clínica inmediata según protocolo institucional."
        elif total >= 5:
            risk, resp = "Medio", "Valoración clínica urgente según protocolo institucional."
        elif any(x == 3 for x in s.values()):
            risk, resp = "Bajo-Medio", "Valoración clínica urgente en sala por un parámetro extremo, según protocolo institucional."
        else:
            risk, resp = "Bajo", "Monitorización según protocolo institucional."
        return NEWS2Result(total, s, risk, resp, ALGORITHM_VERSION, RULES_STATUS)
