"""Tipos básicos del agente: el escritorio remoto y los estados de una tarea."""
from dataclasses import dataclass, field
from typing import Final

# NOTA: estados de una tarea del contrato HTTP (punto 4 de la Tabla H).
EN_CURSO: Final[str] = "en_curso"
TERMINADA: Final[str] = "terminada"
FALLIDA: Final[str] = "fallida"


@dataclass(frozen=True)
class Escritorio:
    """Escritorio remoto al que el agente entra por VNC sobre WebSocket."""

    url: str
    # NOTA: repr=False para que la contraseña no salga en logs, errores ni repr.
    password: str = field(repr=False)