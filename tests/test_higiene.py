"""
Higiene de frontier_agente (C30): leer todos los .py de
agente/frontier_agente/ y comprobar que no contienen cadenas prohibidas y
que los módulos de terceros importados son los permitidos por archivo.
"""
import ast
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parents[1] / "frontier_agente"

# Cadenas prohibidas por la especificación (C30), para todos los archivos.
PROHIBIDAS = [
    "__check",
    "__reset",
    "vncdotool",
    "pyvnc",
    "playwright",
    "selenium",
    "pyautogui",
    "import PIL",
]

# Terceros permitidos (C30). En rfb_protocolo.py, rfb_cliente.py y errores.py
# solo websockets y Crypto; en el resto del paquete (el servidor del bloque 2)
# además fastapi, starlette, pydantic y uvicorn.
TERCEROS_BASE = {"websockets", "Crypto"}
TERCEROS_SERVIDOR = {"fastapi", "starlette", "pydantic", "uvicorn"}
ARCHIVOS_SOLO_BASE = {"rfb_protocolo.py", "rfb_cliente.py", "errores.py"}


def _archivos_py():
    archivos = sorted(CARPETA.glob("*.py"))
    assert archivos, "frontier_agente/ debe contener al menos un archivo .py"
    return archivos


def _terceros_permitidos(archivo: Path) -> set:
    """Conjunto de módulos de terceros permitidos para un archivo dado."""
    if archivo.name in ARCHIVOS_SOLO_BASE:
        return TERCEROS_BASE
    return TERCEROS_BASE | TERCEROS_SERVIDOR


def test_C30_sin_cadenas_prohibidas():
    """C30: ningún .py de frontier_agente contiene __check, __reset,
    vncdotool, pyvnc, playwright, selenium, pyautogui ni import PIL."""
    for archivo in _archivos_py():
        contenido = archivo.read_text(encoding="utf-8")
        for prohibida in PROHIBIDAS:
            assert prohibida not in contenido, \
                f"{archivo.name} contiene la cadena prohibida '{prohibida}'"


def test_C30_importes_de_terceros_permitidos():
    """C30: en rfb_protocolo.py, rfb_cliente.py y errores.py los únicos
    terceros importados son websockets y Crypto; en el resto del paquete
    (el servidor del bloque 2) además fastapi, starlette, pydantic y uvicorn."""
    for archivo in _archivos_py():
        permitidos = (set(sys.stdlib_module_names)
                      | _terceros_permitidos(archivo)
                      | {"frontier_agente"})
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    raiz = alias.name.split(".")[0]
                    assert raiz in permitidos, \
                        f"{archivo.name} importa {alias.name}, que no está permitido"
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level == 0 and nodo.module:
                    raiz = nodo.module.split(".")[0]
                    assert raiz in permitidos, \
                        f"{archivo.name} importa from {nodo.module}, que no está permitido"
