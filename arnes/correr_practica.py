"""Arnés de práctica: corre una prueba de punta a punta contra el escritorio real.

Lee un JSON de prueba, resetea el escritorio, deja que el agente haga la tarea
sobre la pantalla y pregunta al escritorio si quedó como debía. Nunca imprime
la llave, la contraseña, el token ni la URL del escritorio.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

CARPETA_AGENTE = Path(__file__).resolve().parents[1]
if str(CARPETA_AGENTE) not in sys.path:
    # NOTA: permite correrlo como script directo sin instalar nada.
    sys.path.insert(0, str(CARPETA_AGENTE))

from arnes.escritorio_http import check_escritorio, reset_escritorio  # noqa: E402
from frontier_agente.agente import ejecutar_tarea  # noqa: E402
from frontier_agente.resumen import depurar_resumen  # noqa: E402
from frontier_agente.tipos import Escritorio  # noqa: E402

# NOTA: variables de entorno de la corrida (sus valores nunca se imprimen).
VARIABLE_URL = "FRONTIER_ESCRITORIO_URL"
VARIABLE_PASSWORD = "FRONTIER_ESCRITORIO_PASS"
VARIABLE_TOKEN = "FRONTIER_ESCRITORIO_TOKEN"

# NOTA: campos del JSON de prueba, tiempos del protocolo y traza de depuración.
CAMPO_INSTRUCCION = "instruccion"
CAMPO_ESTADO_ESPERADO = "estado_esperado"
CAMPO_PASS = "pass"
CAMPO_CHECKS = "checks"
CAMPO_NOMBRE = "nombre"
CAMPO_OK = "ok"
ESPERA_TRAS_RESET_S = 6.0
VARIABLE_TRAZA = "AGENTE_TRAZA_DIR"
CARPETA_TRAZAS = "logs"
PREFIJO_TRAZA = "traza_"
MARCA_DE_TIEMPO_TRAZA = "%Y%m%d_%H%M%S"

# NOTA: textos del reporte (sin secretos).
TEXTO_OK = "ok"
TEXTO_MAL = "mal"
PLANTILLA_ESTADO_NO_ESPERADO = "el estado {estado} no es el esperado ({esperado})"
MENSAJE_CAMPOS_FALTANTES = (
    "el JSON de prueba necesita los campos {instruccion} y {estado_esperado}"
)


def variables_faltantes() -> list[str]:
    # NOTA: nombres de las variables de entorno que faltan (nunca sus valores).
    return [
        nombre
        for nombre in (VARIABLE_URL, VARIABLE_PASSWORD, VARIABLE_TOKEN)
        if not os.environ.get(nombre)
    ]


def leer_prueba(ruta: Path) -> dict:
    # NOTA: el JSON entero de la prueba es lo que luego se manda al check.
    with ruta.open(encoding="utf-8") as archivo:
        prueba = json.load(archivo)
    if (
        not isinstance(prueba, dict)
        or CAMPO_INSTRUCCION not in prueba
        or CAMPO_ESTADO_ESPERADO not in prueba
    ):
        raise SystemExit(MENSAJE_CAMPOS_FALTANTES)
    return prueba


def _informar_cheques(resultado: dict) -> None:
    # NOTA: el veredicto del check y una línea por chequeo con su nombre y su ok.
    print("check:", TEXTO_OK if resultado.get(CAMPO_PASS) else TEXTO_MAL)
    for chequeo in resultado.get(CAMPO_CHECKS, []):
        if not isinstance(chequeo, dict):
            continue
        paso = TEXTO_OK if chequeo.get(CAMPO_OK) else TEXTO_MAL
        print(f"- {chequeo.get(CAMPO_NOMBRE, 'sin nombre')}: {paso}")


def ruta_traza_por_defecto() -> str:
    # NOTA: la traza de esta corrida: logs/traza_<AAAAMMDD_HHMMSS>; la carpeta la crea el lazo.
    marca = datetime.now().strftime(MARCA_DE_TIEMPO_TRAZA)
    return f"{CARPETA_TRAZAS}/{PREFIJO_TRAZA}{marca}"


def preparar_traza() -> str:
    # NOTA: AGENTE_TRAZA_DIR manda si ya existe; si no, se crea la ruta por defecto
    # y se imprime (no es secreto) para poder revisar la depuración de la corrida.
    ruta = os.environ.get(VARIABLE_TRAZA) or ruta_traza_por_defecto()
    os.environ[VARIABLE_TRAZA] = ruta
    print("traza:", ruta)
    return ruta


def _informar(estado: str, resumen: str, resultado: dict, esperado: str) -> None:
    # NOTA: estado, resumen ya depurado, veredicto del check y aviso si no era lo esperado.
    print("estado:", estado)
    print("resumen:")
    print(resumen)
    _informar_cheques(resultado)
    if estado != esperado:
        print(PLANTILLA_ESTADO_NO_ESPERADO.format(estado=estado, esperado=esperado))


async def correr(prueba: dict) -> None:
    # NOTA: reset, espera de repintado, tarea del agente y check final; la
    # contraseña y el token solo viven en las llamadas y en la depuración.
    url = os.environ[VARIABLE_URL]
    password = os.environ[VARIABLE_PASSWORD]
    token = os.environ[VARIABLE_TOKEN]
    await reset_escritorio(url, token)
    await asyncio.sleep(ESPERA_TRAS_RESET_S)
    escritorio = Escritorio(url=url, password=password)
    estado, resumen = await ejecutar_tarea(prueba[CAMPO_INSTRUCCION], escritorio)
    resumen_limpio = depurar_resumen(resumen, [password, token])
    resultado = await check_escritorio(url, token, prueba)
    _informar(estado, resumen_limpio, resultado, prueba[CAMPO_ESTADO_ESPERADO])


def main() -> None:
    # NOTA: argparse para la ruta del JSON de prueba; las llaves salen del entorno.
    analizador = argparse.ArgumentParser(
        description="Corre una prueba de práctica contra el escritorio real."
    )
    analizador.add_argument("prueba", type=Path, help="archivo JSON de la prueba")
    argumentos = analizador.parse_args()
    faltan = variables_faltantes()
    if faltan:
        raise SystemExit("faltan las variables de entorno: " + ", ".join(faltan))
    preparar_traza()
    asyncio.run(correr(leer_prueba(argumentos.prueba)))


if __name__ == "__main__":
    main()
