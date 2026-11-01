from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator
from clinical.age import age_on, today_bogota
from clinical.algorithms.news2.calculator import ConsciousnessLevel
from clinical.special_populations import Pregnancy

IDPAT = r"^[A-Za-z0-9_-]{1,64}$"
Role = Literal["admin", "clinician", "auditor"]

class Strict(BaseModel):
    # extra="forbid": un campo con typo (p. ej. spo2_scale2) es 422, no un default silencioso.
    # NO usar str_strip_whitespace: recortaría contraseñas.
    model_config = ConfigDict(extra="forbid")

class PatientIn(Strict):
    patient_id: str = Field(pattern=IDPAT)
    full_name: str = Field(min_length=1, max_length=200)
    age: StrictInt | None = Field(None, ge=0, le=120)   # opcional si se da birth_date (se deriva)
    birth_date: date | None = None
    gender: Literal["male", "female", "other", "unknown"]

    @field_validator("birth_date", mode="before")
    @classmethod
    def _iso_string_only(cls, v):
        if v is not None and not isinstance(v, str):    # date en modo lax aceptaría enteros (timestamps)
            raise ValueError("birth_date debe ser una cadena ISO AAAA-MM-DD.")
        return v

    @model_validator(mode="after")
    def _age_consistency(self):
        if self.birth_date is None:
            if self.age is None: raise ValueError("Indica age o birth_date.")
            return self
        today = today_bogota()
        if self.birth_date > today: raise ValueError("birth_date no puede ser futura.")
        derived = age_on(self.birth_date, today)
        if derived > 120: raise ValueError("birth_date implausible.")
        if self.age is not None and self.age != derived: raise ValueError("age no coincide con birth_date.")
        self.age = derived
        return self

class VitalsIn(Strict):
    respiratory_rate: StrictInt = Field(ge=1, le=70)
    oxygen_saturation: StrictInt = Field(ge=50, le=100)
    supplemental_oxygen: StrictBool
    spo2_scale_2: StrictBool                      # sin default: debe declararse explícitamente
    systolic_bp: StrictInt = Field(ge=40, le=300)
    heart_rate: StrictInt = Field(ge=20, le=250)
    consciousness: ConsciousnessLevel
    temperature: float = Field(ge=30.0, le=45.0, allow_inf_nan=False)

    @field_validator("temperature", mode="before")
    @classmethod
    def _numeric_only(cls, v):
        # float en modo lax aceptaría "37.0" (str) o True; aquí solo números JSON (37 y 37.0 valen)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("La temperatura debe ser numérica.")
        return v

    @field_validator("temperature")
    @classmethod
    def _one_decimal(cls, v: float) -> float:
        return round(v, 1)

class EvaluateIn(Strict):
    patient_id: str = Field(pattern=IDPAT)
    vitals: VitalsIn
    pregnancy: Pregnancy              # sin default: debe declararse (yes | no | unknown)
    spinal_cord_injury: StrictBool    # sin default

class UserCreate(Strict):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")
    password: str = Field(min_length=12, max_length=128)
    role: Role

class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class PasswordChange(Strict):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

class BreakGlassIn(Strict):
    reason: str = Field(min_length=15, max_length=200)

    @field_validator("reason")
    @classmethod
    def _meaningful(cls, v: str) -> str:
        v = " ".join(v.split())               # no vale rellenar con espacios
        if len(v) < 15: raise ValueError("Describe el motivo con al menos 15 caracteres.")
        return v
