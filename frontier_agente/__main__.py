"""Arranque del servicio: uvicorn con 1 worker, host de HOST y puerto de PORT."""
import os

import uvicorn

from frontier_agente.agente import ejecutar_tarea
from frontier_agente.errores import ErrorConfiguracion
from frontier_agente.servidor import NOMBRE_VARIABLE_OPENROUTER, crear_app

# NOTA: despliegue de la prosa 7: 1 worker, 127.0.0.1 (HOST lo cambia), puerto de PORT (8000 por defecto).
NOMBRE_VARIABLE_PUERTO = "PORT"
NOMBRE_VARIABLE_HOST = "HOST"
PUERTO_POR_DEFECTO = 8000
ANFITRION_POR_DEFECTO = "127.0.0.1"
TRABAJADORES = 1
MENSAJE_FALTA_LLAVE = "falta la variable de entorno {variable}"
MENSAJE_PUERTO_INVALIDO = "La variable {variable} no es un puerto válido"


def puerto_de_entorno() -> int:
    """Lee PORT (8000 si no existe); si existe pero no es un puerto, ErrorConfiguracion."""
    # NOTA: el texto crudo no se loguea: un valor inválido puede traer cualquier cosa.
    texto = os.environ.get(NOMBRE_VARIABLE_PUERTO, str(PUERTO_POR_DEFECTO))
    try:
        return int(texto)
    except ValueError:
        raise ErrorConfiguracion(
            MENSAJE_PUERTO_INVALIDO.format(variable=NOMBRE_VARIABLE_PUERTO)
        ) from None


def anfitrion_de_entorno() -> str:
    """Prosa 7: escucha en 127.0.0.1 salvo que la variable HOST diga otra cosa."""
    # NOTA: el túnel llega por 127.0.0.1; HOST permite cambiarlo sin tocar el código.
    return os.environ.get(NOMBRE_VARIABLE_HOST) or ANFITRION_POR_DEFECTO


def main() -> None:
    """Arranca el servicio con el agente de verdad; sin OPENROUTER_API_KEY no arranca."""
    # NOTA: la llave del modelo se exige aquí y solo se nombra la variable, nunca su valor;
    # el token del equipo lo sigue resolviendo crear_app.
    if not os.environ.get(NOMBRE_VARIABLE_OPENROUTER):
        raise ErrorConfiguracion(
            MENSAJE_FALTA_LLAVE.format(variable=NOMBRE_VARIABLE_OPENROUTER)
        )
    uvicorn.run(
        crear_app(ejecutar_tarea),
        host=anfitrion_de_entorno(),
        port=puerto_de_entorno(),
        workers=TRABAJADORES,
    )


if __name__ == "__main__":
    main()
