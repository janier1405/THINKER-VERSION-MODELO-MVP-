import os
from pathlib import Path


def secret(name: str, default: str | None = None) -> str | None:
    """Lee NAME_FILE (secreto montado como archivo) o, si no existe, la variable NAME."""
    f = os.getenv(f"{name}_FILE")
    return Path(f).read_text().strip() if f else os.getenv(name, default)
