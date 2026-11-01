from datetime import date, datetime, timedelta, timezone

BOGOTA = timezone(timedelta(hours=-5))   # Colombia no tiene horario de verano; evita depender de tzdata en la imagen slim

def today_bogota() -> date:
    return datetime.now(BOGOTA).date()

def age_on(birth: date, on: date) -> int:
    """Edad cumplida. Un nacido el 29-feb cumple años el 1-mar en años no bisiestos (convención civil colombiana)."""
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))
