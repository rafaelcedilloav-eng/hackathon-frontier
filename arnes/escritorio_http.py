"""Arnés HTTP del escritorio: la única vía hacia /__reset y /__check (fuera de frontier_agente)."""

import asyncio
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from frontier_agente.errores import ErrorConexion

RUTA_RESET = "/__reset"
RUTA_CHECK = "/__check"
TOPE_RESET_S = 10.0
TOPE_CHECK_S = 10.0
TIPO_CONTENIDO_JSON = "application/json"
ESQUEMAS_WS_A_HTTP = {"ws": "http", "wss": "https"}
MENSAJE_CHECK_RECHAZADO = "check rechazado (código HTTP {codigo})"
MENSAJE_CHECK_FALLO = "check falló ({clase})"
MENSAJE_CHECK_NO_JSON = "la respuesta del check no es un objeto JSON"


def url_http_desde_ws(url_ws: str) -> str:
    # NOTA: ws->http y wss->https conservando host y puerto, sin la ruta.
    partes = urlsplit(url_ws)
    if partes.scheme not in ESQUEMAS_WS_A_HTTP or not partes.netloc:
        raise ValueError(f"URL de WebSocket inválida (esquema: {partes.scheme!r})")
    return f"{ESQUEMAS_WS_A_HTTP[partes.scheme]}://{partes.netloc}"


def _post_reset(url: str, token: str) -> None:
    # NOTA: bloqueante (urllib); asyncio.to_thread lo llama para no frenar el evento.
    peticion = urllib.request.Request(
        url, data=b"", method="POST", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(peticion, timeout=TOPE_RESET_S):
            pass  # un 2xx basta: el reset no devuelve cuerpo
    except urllib.error.HTTPError as exc:
        # NOTA: la causa trae la URL; con from None no se encadena.
        raise ErrorConexion(f"reset rechazado (código HTTP {exc.code})") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        # NOTA: la causa trae la URL; con from None no se encadena.
        raise ErrorConexion(f"reset falló ({type(exc).__name__})") from None


async def reset_escritorio(url_ws: str, token: str) -> None:
    # NOTA: único lugar del arnés que llama a /__reset; manda el token como Bearer.
    url = url_http_desde_ws(url_ws) + RUTA_RESET
    await asyncio.to_thread(_post_reset, url, token)


def _post_check(url: str, token: str, cuerpo: dict) -> dict:
    # NOTA: bloqueante (urllib); asyncio.to_thread lo llama para no frenar el evento.
    datos = json.dumps(cuerpo).encode("utf-8")
    peticion = urllib.request.Request(
        url, data=datos, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": TIPO_CONTENIDO_JSON})
    try:
        with urllib.request.urlopen(peticion, timeout=TOPE_CHECK_S) as respuesta_http:
            texto = respuesta_http.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # NOTA: la causa trae la URL; con from None no se encadena.
        raise ErrorConexion(MENSAJE_CHECK_RECHAZADO.format(codigo=exc.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        # NOTA: solo el nombre de la clase; ni la URL ni el detalle del fallo.
        raise ErrorConexion(MENSAJE_CHECK_FALLO.format(clase=type(exc).__name__)) from None
    try:
        resultado = json.loads(texto)
    except json.JSONDecodeError:
        raise ErrorConexion(MENSAJE_CHECK_NO_JSON) from None
    if not isinstance(resultado, dict):
        raise ErrorConexion(MENSAJE_CHECK_NO_JSON) from None
    return resultado


async def check_escritorio(url_ws: str, token: str, cuerpo: dict) -> dict:
    # NOTA: único lugar del arnés que llama a /__check; manda el JSON entero de la prueba
    # y devuelve la respuesta (pass y la lista de checks) tal cual la dio el escritorio.
    url = url_http_desde_ws(url_ws) + RUTA_CHECK
    return await asyncio.to_thread(_post_check, url, token, cuerpo)
