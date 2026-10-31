"""
Pruebas del arnés (tabla H): arnes.escritorio_http.

H1-H3: url_http_desde_ws (valores literales de la tabla).
H4: reset_escritorio contra un servidor HTTP local de prueba.
"""
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from arnes.escritorio_http import reset_escritorio, url_http_desde_ws
from frontier_agente.errores import ErrorConexion


# ------------------------------------------------------------ H1 a H3
def test_H1_url_http_desde_ws_wss():
    """H1: url_http_desde_ws("wss://escritorio.ejemplo.com/websockify") =
    "https://escritorio.ejemplo.com"."""
    assert url_http_desde_ws("wss://escritorio.ejemplo.com/websockify") \
        == "https://escritorio.ejemplo.com"


def test_H2_url_http_desde_ws_ws():
    """H2: url_http_desde_ws("ws://127.0.0.1:6080/websockify") =
    "http://127.0.0.1:6080"."""
    assert url_http_desde_ws("ws://127.0.0.1:6080/websockify") \
        == "http://127.0.0.1:6080"


def test_H3_url_http_desde_ws_invalidas():
    """H3: url_http_desde_ws("https://x.com/websockify") y ("") -> ValueError."""
    with pytest.raises(ValueError):
        url_http_desde_ws("https://x.com/websockify")
    with pytest.raises(ValueError):
        url_http_desde_ws("")


# ----------------------------------------------------------------- H4
class _ServidorHTTPDePrueba:
    """Servidor HTTP local que registra cada petición y responde un código fijo."""

    def __init__(self, codigo_respuesta: int):
        registro = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                largo = int(self.headers.get("Content-Length", 0))
                cuerpo = self.rfile.read(largo)
                registro.ultima_peticion = {
                    "metodo": self.command,
                    "ruta": self.path,
                    "authorization": self.headers.get("Authorization", ""),
                    "cuerpo": cuerpo,
                }
                registro.contador_peticiones += 1
                self.send_response(registro.codigo_respuesta)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.codigo_respuesta = codigo_respuesta
        self.ultima_peticion = None
        self.contador_peticiones = 0
        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self._hilo = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._hilo.start()

    @property
    def url_ws(self) -> str:
        puerto = self._httpd.server_address[1]
        return f"ws://127.0.0.1:{puerto}/websockify"

    def cerrar(self):
        self._httpd.shutdown()
        self._httpd.server_close()


def test_H4_reset_escritorio_respuesta_200():
    """H4: reset_escritorio manda POST /__reset con Authorization: Bearer
    <token>; con respuesta 200 no lanza."""
    servidor = _ServidorHTTPDePrueba(200)
    try:
        token = "token-de-prueba-abc123"
        asyncio.run(reset_escritorio(servidor.url_ws, token))
        assert servidor.contador_peticiones == 1
        peticion = servidor.ultima_peticion
        assert peticion["metodo"] == "POST"
        assert peticion["ruta"] == "/__reset"
        assert peticion["authorization"] == f"Bearer {token}"
    finally:
        servidor.cerrar()


def test_H4_reset_escritorio_respuesta_401():
    """H4: con respuesta 401 lanza ErrorConexion, y el token no aparece en
    el mensaje."""
    servidor = _ServidorHTTPDePrueba(401)
    try:
        token = "token-secreto-XYZ-9981"
        with pytest.raises(ErrorConexion) as excinfo:
            asyncio.run(reset_escritorio(servidor.url_ws, token))
        assert token not in str(excinfo.value)
        assert servidor.contador_peticiones == 1
    finally:
        servidor.cerrar()
