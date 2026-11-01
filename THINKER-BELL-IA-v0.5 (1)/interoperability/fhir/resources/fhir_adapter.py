"""Generación inicial de recursos FHIR R4; requiere validación con un validador FHIR.
HEREDADO Y NO CONECTADO: no usarlo en producción (ver docs/ROADMAP_FHIR_AI.md)."""
from datetime import datetime, timezone
TriageRequestSchema = object  # PENDIENTE: adaptar al esquema v2; adaptador no conectado ni validado

LOINC = {
    "respiratory_rate": ("9279-1", "Respiratory rate", "/min"),
    "oxygen_saturation": ("2708-6", "Oxygen saturation in Arterial blood", "%"),
    "systolic_bp": ("8480-6", "Systolic blood pressure", "mm[Hg]"),
    "heart_rate": ("8867-4", "Heart rate", "/min"),
    "temperature": ("8310-5", "Body temperature", "Cel"),
}

class FHIRAdapter:
    @staticmethod
    def to_fhir_patient(payload: TriageRequestSchema) -> dict:
        gender = {"male": "male", "female": "female", "other": "other", "unknown": "unknown"}[payload.patient.gender]
        return {"resourceType": "Patient", "id": payload.patient.patient_id, "active": True,
                "name": [{"use": "official", "text": payload.patient.full_name}], "gender": gender,
                "birthDate": None}

    @staticmethod
    def to_fhir_observations(payload: TriageRequestSchema, evaluation_id: str) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat()
        patient_ref = f"Patient/{payload.patient.patient_id}"
        entries = []
        for key, (code, display, unit) in LOINC.items():
            value = getattr(payload.vitals, key)
            entries.append({"resource": {
                "resourceType": "Observation", "id": f"{evaluation_id}-{key}", "status": "final",
                "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs", "display": "Vital Signs"}]}],
                "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
                "subject": {"reference": patient_ref}, "effectiveDateTime": timestamp,
                "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit}
            }})
        return {"resourceType": "Bundle", "type": "collection", "entry": entries}
