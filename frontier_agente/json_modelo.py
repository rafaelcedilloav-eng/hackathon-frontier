"""Extrae el primer objeto JSON de una respuesta del modelo, sin confiar en ella."""
import json

from frontier_agente.tipos_agente import ErrorModelo

MENSAJE_SIN_OBJETO = "la respuesta del modelo no contiene un objeto JSON"
MENSAJE_OBJETO_INCOMPLETO = "la respuesta del modelo no contiene un objeto JSON completo"
MENSAJE_OBJETO_INVALIDO = "la respuesta del modelo no contiene un objeto JSON válido"
MENSAJE_NO_ES_OBJETO = "la respuesta del modelo no es un objeto JSON"


def _fin_de_objeto(texto: str, inicio: int) -> int | None:
    # NOTA: busca la llave } que cierra en balance la { de inicio; respeta
    # comillas y escapes para no confundirse con llaves dentro de cadenas.
    profundidad = 0
    dentro_de_cadena = False
    hay_escape = False
    for indice in range(inicio, len(texto)):
        caracter = texto[indice]
        if dentro_de_cadena:
            if hay_escape:
                hay_escape = False
            elif caracter == "\\":
                hay_escape = True
            elif caracter == '"':
                dentro_de_cadena = False
        elif caracter == '"':
            dentro_de_cadena = True
        elif caracter == "{":
            profundidad += 1
        elif caracter == "}":
            profundidad -= 1
            if profundidad == 0:
                return indice
    return None


def extraer_json(texto: str) -> dict:
    # NOTA: recorta del primer { a su } balanceado y parsea; cualquier
    # problema es ErrorModelo porque el texto del modelo nunca es de confiar.
    inicio = texto.find("{")
    if inicio == -1:
        raise ErrorModelo(MENSAJE_SIN_OBJETO)
    fin = _fin_de_objeto(texto, inicio)
    if fin is None:
        raise ErrorModelo(MENSAJE_OBJETO_INCOMPLETO)
    try:
        objeto = json.loads(texto[inicio:fin + 1])
    except (ValueError, RecursionError):
        # NOTA: JSONDecodeError es ValueError; enteros gigantes dan ValueError
        # y anidación extrema da RecursionError: todos son respuesta ilegible.
        raise ErrorModelo(MENSAJE_OBJETO_INVALIDO) from None
    if not isinstance(objeto, dict):
        raise ErrorModelo(MENSAJE_NO_ES_OBJETO)
    return objeto
