"""Prueba real del cliente RFB contra el escritorio vivo (la corre el director).

Sale con 2 si falta una variable de entorno, 1 si algo falla o la captura
sale negra, y 0 si todo sale bien. Imprime solo la ruta, el tamaño de la
imagen, la fracción no negra y si quedó quieta: nunca la URL, la
contraseña ni el token.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

CARPETA_AGENTE = Path(__file__).resolve().parents[1]
if str(CARPETA_AGENTE) not in sys.path:
    # NOTA: permite correrlo como script directo sin instalar nada.
    sys.path.insert(0, str(CARPETA_AGENTE))

from arnes.escritorio_http import reset_escritorio  # noqa: E402
from frontier_agente.errores import ErrorConexion, ErrorVNC  # noqa: E402
from frontier_agente.rfb_cliente import ClienteRFB  # noqa: E402
from frontier_agente.rfb_protocolo import fraccion_no_negra, png_desde_bgrx  # noqa: E402

VARIABLE_URL = "FRONTIER_ESCRITORIO_URL"
VARIABLE_PASSWORD = "FRONTIER_ESCRITORIO_PASS"
VARIABLE_TOKEN = "FRONTIER_ESCRITORIO_TOKEN"

INTENTOS_CONEXION = 10
ESPERA_REINTENTO_S = 2.0
FRACCION_MINIMA = 0.05
CARPETA_LOGS = Path("logs")
CODIGO_OK = 0
CODIGO_FALLO = 1
CODIGO_FALTA_VARIABLE = 2


def _variables_faltantes() -> list[str]:
    # NOTA: nombres de las variables de entorno que faltan (nunca sus valores).
    return [nombre for nombre in (VARIABLE_URL, VARIABLE_PASSWORD, VARIABLE_TOKEN)
            if not os.environ.get(nombre)]


def _guardar_captura(png: bytes) -> Path:
    # NOTA: escribe la captura con marca AAAAMMDD_HHMMSS dentro de logs/.
    CARPETA_LOGS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = CARPETA_LOGS / f"captura_real_{marca}.png"
    ruta.write_bytes(png)
    return ruta


async def _conectar_con_reintentos(url: str, password: str) -> ClienteRFB:
    # NOTA: hasta 10 intentos, uno cada 2 s: el navegador se reinicia tras el reset.
    cliente = ClienteRFB(url, password)
    for intento in range(1, INTENTOS_CONEXION + 1):
        try:
            await cliente.conectar()
            return cliente
        except ErrorVNC:
            await cliente.cerrar()
            if intento < INTENTOS_CONEXION:
                await asyncio.sleep(ESPERA_REINTENTO_S)
    raise ErrorConexion(f"no se pudo conectar tras {INTENTOS_CONEXION} intentos")


async def _prueba_real() -> int:
    # NOTA: reset, conectar, esperar quieta, capturar, medir y reportar; cierra siempre.
    faltan = _variables_faltantes()
    if faltan:
        for nombre in faltan:
            print(f"falta la variable de entorno {nombre}")
        return CODIGO_FALTA_VARIABLE
    url = os.environ[VARIABLE_URL]
    password = os.environ[VARIABLE_PASSWORD]
    token = os.environ[VARIABLE_TOKEN]
    await reset_escritorio(url, token)
    cliente = None
    try:
        cliente = await _conectar_con_reintentos(url, password)
        quieta, _png = await cliente.esperar_quieta()
        bgrx = await cliente.captura_bgrx()
        png = png_desde_bgrx(bgrx, cliente.ancho, cliente.alto)
        fraccion = fraccion_no_negra(bgrx)
        ruta = _guardar_captura(png)
        print(f"ruta: {ruta}")
        print(f"tamaño: {len(png)} bytes")
        print(f"fracción no negra: {fraccion:.4f}")
        print(f"quieta: {'sí' if quieta else 'no'}")
        if fraccion < FRACCION_MINIMA:
            print("la captura salió negra")
            return CODIGO_FALLO
        return CODIGO_OK
    finally:
        if cliente is not None:
            await cliente.cerrar()


def main() -> int:
    # NOTA: punto de entrada; cualquier fallo acaba en código 1 sin secretos.
    try:
        return asyncio.run(_prueba_real())
    except Exception as exc:
        print(f"falló la prueba real: {type(exc).__name__}")
        return CODIGO_FALLO


if __name__ == "__main__":
    sys.exit(main())
