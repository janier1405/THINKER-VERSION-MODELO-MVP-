from datetime import date, datetime, timedelta, timezone
from sqlalchemy import Date, DateTime, func, literal_column
from clinical.age import BOGOTA

_OFF_H = int(-BOGOTA.utcoffset(None).total_seconds() // 3600)   # 5; constante del código, nunca entrada de usuario
_MAX_DAY = date(9999, 12, 30)                                     # evita OverflowError al sumar un día

def as_utc(dt: datetime) -> datetime:
    """Siempre UTC con zona explícita. SQLite devuelve datetimes naive (el navegador los leería como hora local) y
    PostgreSQL devuelve timestamptz en la zona de la sesión (p. ej. +09:00): la salida de la API no debe depender de ello."""
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

def day_start_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=BOGOTA).astimezone(timezone.utc)

def day_end_utc(d: date) -> datetime:
    """Inicio (exclusivo) del día siguiente. Sin horario de verano, un día local dura exactamente 24 h."""
    return day_start_utc(min(d, _MAX_DAY)) + timedelta(days=1)

def local_day(db, col):
    """Día calendario de Bogotá como expresión SQL, independiente del TimeZone de la sesión."""
    if db.get_bind().dialect.name == "postgresql":
        utc_wall = func.timezone("UTC", col, type_=DateTime())     # timestamptz -> hora de pared en UTC
        return func.date(utc_wall - literal_column(f"INTERVAL '{_OFF_H} hours'"), type_=Date)
    return func.date(func.datetime(col, literal_column(f"'-{_OFF_H} hours'")), type_=Date)   # SQLite guarda UTC
