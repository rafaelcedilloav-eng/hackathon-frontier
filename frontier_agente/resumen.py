"""Depuración de resúmenes: ningún secreto del servicio sale en ellos."""
from typing import Final

# NOTA: marca que sustituye a cada secreto (Tabla R).
MARCA_OCULTO: Final[str] = "[oculto]"


def depurar_resumen(resumen: str, secretos: list[str]) -> str:
    """Sustituye cada aparición de cada secreto por MARCA_OCULTO (Tabla R)."""
    # NOTA: los secretos vacíos se ignoran y los más largos van primero (R5):
    # así "clave2" se reemplaza antes que "clave" y no quedan trozos a medias.
    ordenados = sorted((secreto for secreto in secretos if secreto), key=len, reverse=True)
    for secreto in ordenados:
        resumen = resumen.replace(secreto, MARCA_OCULTO)
    return resumen