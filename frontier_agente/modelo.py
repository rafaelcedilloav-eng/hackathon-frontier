"""Llama al modelo por OpenRouter y convierte su respuesta en RespuestaModelo."""
import asyncio
import base64
import copy
import json
import math
import os
import urllib.request
from collections.abc import Awaitable, Callable

from frontier_agente.errores import ErrorConfiguracion
from frontier_agente.tipos_agente import ErrorModelo, RespuestaModelo

MODELO_OJOS = "anthropic/claude-haiku-5.5"
MODELO_ATASCO = "anthropic/claude-sonnet-5.5"
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
VARIABLE_LLAVE = "OPENROUTER_API_KEY"
TOPE_LLAMADA_S = 60.0

TIPO_CONTENIDO_JSON = "application/json"
MENSAJE_SIN_CHOICES = "respuesta del modelo sin choices"
MENSAJE_SIN_MENSAJE = "respuesta del modelo sin message"
MENSAJE_CONTENIDO_INVALIDO = "respuesta del modelo con contenido ilegible"
MENSAJE_RESPUESTA_MALFORMADA = "respuesta del modelo malformada"
PREFIJO_ERROR_PROVEEDOR = "respuesta del modelo con error"
COSTO_POR_OMISION = 0.0

# NOTA: tipo de `enviar`: recibe el cuerpo y el tope, devuelve la respuesta cruda.
TipoEnviar = Callable[[dict, float], Awaitable[dict]]


def _sufijo_codigo_http(codigo: object) -> str:
    # NOTA: única regla para mostrar códigos de error: solo enteros; el
    # texto del proveedor nunca se incluye aunque venga en ese campo.
    if isinstance(codigo, bool) or not isinstance(codigo, int):
        return ""
    return f" (HTTP {codigo})"


def _contenido_de_partes(partes: list) -> str:
    # NOTA: cada parte de texto exige un "text" de tipo texto; una lista sin
    # ninguna parte de texto válida es una respuesta ilegible (M17).
    textos = []
    hay_parte_de_texto = False
    for parte in partes:
        if not isinstance(parte, dict) or parte.get("type") != "text":
            continue
        hay_parte_de_texto = True
        texto = parte.get("text")
        if not isinstance(texto, str):
            raise ErrorModelo(MENSAJE_CONTENIDO_INVALIDO)
        textos.append(texto)
    if not hay_parte_de_texto:
        raise ErrorModelo(MENSAJE_CONTENIDO_INVALIDO)
    return "".join(textos)


def construir_cuerpo(mensajes: list[dict], imagen_png: bytes | None, *, modelo: str, esfuerzo: str) -> dict:
    # NOTA: arma el cuerpo del chat de OpenRouter; copia la entrada para no
    # modificar la lista del llamador (M3) y solo el último mensaje lleva imagen.
    mensajes_salida = copy.deepcopy(mensajes)
    if imagen_png is not None and mensajes_salida:
        imagen_b64 = base64.b64encode(imagen_png).decode("ascii")
        ultimo = mensajes_salida[-1]
        # NOTA: la imagen se adjunta como data URL después del texto original.
        ultimo["content"] = [
            {"type": "text", "text": ultimo["content"]},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + imagen_b64}},
        ]
    return {
        "model": modelo,
        "messages": mensajes_salida,
        "temperature": 0,
        "reasoning": {"effort": esfuerzo},
        "usage": {"include": True},
    }


def _texto_de_choices(choices: object) -> str:
    # NOTA: extrae choices[0].message.content sin confiar en la forma:
    # cualquier pieza ausente o de tipo raro es ErrorModelo, nunca KeyError.
    if not isinstance(choices, list) or not choices:
        raise ErrorModelo(MENSAJE_SIN_CHOICES)
    eleccion = choices[0]
    if not isinstance(eleccion, dict):
        raise ErrorModelo(MENSAJE_SIN_MENSAJE)
    mensaje = eleccion.get("message")
    if not isinstance(mensaje, dict):
        raise ErrorModelo(MENSAJE_SIN_MENSAJE)
    contenido = mensaje.get("content")
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return _contenido_de_partes(contenido)
    raise ErrorModelo(MENSAJE_CONTENIDO_INVALIDO)


def _costo_de(uso: object) -> float:
    # NOTA: costo ausente, null, ilegible, no finito (NaN, Infinity) o tan
    # grande que no cabe en float (10**400) vale 0.0 sin lanzar nada (M18).
    if not isinstance(uso, dict):
        return COSTO_POR_OMISION
    costo = uso.get("cost")
    if isinstance(costo, bool) or not isinstance(costo, (int, float)):
        return COSTO_POR_OMISION
    try:
        costo_float = float(costo)
    except OverflowError:
        return COSTO_POR_OMISION
    if not math.isfinite(costo_float):
        return COSTO_POR_OMISION
    return costo_float


def leer_respuesta(respuesta: dict) -> RespuestaModelo:
    # NOTA: valida la respuesta del proveedor; toda malformación es
    # ErrorModelo y el mensaje lleva solo el código HTTP, nunca detalles.
    if not isinstance(respuesta, dict):
        raise ErrorModelo(MENSAJE_RESPUESTA_MALFORMADA)
    if "error" in respuesta:
        error = respuesta["error"]
        codigo = error.get("code") if isinstance(error, dict) else None
        raise ErrorModelo(PREFIJO_ERROR_PROVEEDOR + _sufijo_codigo_http(codigo))
    texto = _texto_de_choices(respuesta.get("choices"))
    return RespuestaModelo(texto, _costo_de(respuesta.get("usage")))


def _mensaje_fallo(excepcion: Exception) -> str:
    # NOTA: solo el nombre de la clase y el código HTTP; el mensaje original
    # de la excepción puede traer secretos y nunca se incluye.
    codigo = getattr(excepcion, "code", None)
    return f"llamada al modelo falló: {type(excepcion).__name__}{_sufijo_codigo_http(codigo)}"


def _enviar_http(cuerpo: dict, tope_s: float, llave: str) -> dict:
    # NOTA: envío síncrono con urllib; la llave solo vive en el encabezado
    # de esta petición y nunca sale en errores ni en el cuerpo recibido.
    datos_json = json.dumps(cuerpo).encode("utf-8")
    peticion = urllib.request.Request(
        URL_OPENROUTER,
        data=datos_json,
        headers={"Authorization": "Bearer " + llave, "Content-Type": TIPO_CONTENIDO_JSON},
    )
    with urllib.request.urlopen(peticion, timeout=tope_s) as respuesta_http:
        return json.loads(respuesta_http.read().decode("utf-8"))


async def _enviar_por_defecto(cuerpo: dict, tope_s: float, llave: str) -> dict:
    # NOTA: urllib es bloqueante, así que corre en un hilo con asyncio.to_thread.
    return await asyncio.to_thread(_enviar_http, cuerpo, tope_s, llave)


def _enviar_con_llave(llave: str) -> TipoEnviar:
    # NOTA: fábrica que captura la llave por cierre; desde aquí sí viaja como
    # argumento privado a _enviar_http, donde solo se usa en el encabezado
    # Authorization y nunca en logs, excepciones ni el cuerpo de la petición.

    async def enviador(cuerpo: dict, tope_s: float) -> dict:
        # NOTA: envoltura async de la función propia; la llave solo existe
        # aquí dentro, capturada por el cierre, y no se recibe ni se devuelve.
        return await _enviar_por_defecto(cuerpo, tope_s, llave)

    return enviador


async def llamar_modelo(
    mensajes: list[dict],
    imagen_png: bytes | None = None,
    *,
    modelo: str = MODELO_OJOS,
    esfuerzo: str = "low",
    tope_s: float = TOPE_LLAMADA_S,
    enviar: TipoEnviar | None = None,
) -> RespuestaModelo:
    # NOTA: construye el cuerpo, lo entrega a `enviar` (falso en pruebas) y
    # traduce la respuesta; la llave se lee del entorno justo al llamar.
    cuerpo = construir_cuerpo(mensajes, imagen_png, modelo=modelo, esfuerzo=esfuerzo)
    if enviar is None:
        # NOTA: la llave se lee y se limpia justo al llamar; sin llave no hay
        # llamada y el ErrorConfiguracion nombra solo la variable, nunca valores.
        llave = (os.environ.get(VARIABLE_LLAVE) or "").strip()
        if not llave:
            raise ErrorConfiguracion(f"falta la variable de entorno {VARIABLE_LLAVE}")
        enviador = _enviar_con_llave(llave)
    else:
        enviador = enviar
    fallo: str | None = None
    try:
        respuesta = await enviador(cuerpo, tope_s)
    except asyncio.CancelledError:
        raise
    except Exception as excepcion:
        # NOTA: solo se guarda el mensaje seguro; la excepción original no se
        # propaga ni se encadena (su texto puede traer la llave en la cabecera).
        fallo = _mensaje_fallo(excepcion)
    if fallo is not None:
        # NOTA: se lanza FUERA del except y con from None para que la
        # excepción original no quede encadenada como causa ni contexto.
        raise ErrorModelo(fallo) from None
    return leer_respuesta(respuesta)
