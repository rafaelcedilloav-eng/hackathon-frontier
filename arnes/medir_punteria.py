"""Arnés desechable: mide la puntería de un modelo con ojos contra el escritorio real.

Para cada caso de casos_punteria.json: resetea el escritorio, prepara la
pantalla, pregunta al modelo por la posición de la descripción en dos modos
(norm1000 y pixeles), mide el error contra la caja, hace clic en la
predicción norm1000 y anota si la pantalla cambió. Nunca imprime ni escribe
la llave, la contraseña, el token ni la URL del escritorio.
"""

import argparse
import asyncio
import base64
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

CARPETA_AGENTE = Path(__file__).resolve().parents[1]
if str(CARPETA_AGENTE) not in sys.path:
    # NOTA: permite correrlo como script directo sin instalar nada.
    sys.path.insert(0, str(CARPETA_AGENTE))

from arnes.escritorio_http import reset_escritorio  # noqa: E402
from frontier_agente.rfb_cliente import ClienteRFB  # noqa: E402
from frontier_agente.rfb_protocolo import png_desde_bgrx  # noqa: E402

# NOTA: variables de entorno que alimentan la corrida (nunca sus valores al imprimir).
VARIABLE_URL = "FRONTIER_ESCRITORIO_URL"
VARIABLE_PASSWORD = "FRONTIER_ESCRITORIO_PASS"
VARIABLE_TOKEN = "FRONTIER_ESCRITORIO_TOKEN"
VARIABLE_API_KEY = "OPENROUTER_API_KEY"

# NOTA: parámetros de la llamada al modelo, tal como los fija el encargo.
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
MODELO_POR_DEFECTO = "anthropic/claude-haiku-5.5"
TOPE_LLAMADA_S = 60.0
PREFIJO_DATA_URL = "data:image/png;base64,"
ESFUERZO_RAZONAMIENTO = "low"

# NOTA: tiempos del protocolo de medición contra el escritorio.
ESPERA_TRAS_RESET_S = 6.0
PAUSA_TRAS_CLIC_S = 1.5

# NOTA: geometría fija de la pantalla de los casos y de la escala normalizada.
ANCHO_PANTALLA_PX = 1280
ALTO_PANTALLA_PX = 800
ESCALA_NORMALIZADA = 1000

# NOTA: los dos modos de respuesta del modelo y su instrucción.
MODO_NORM = "norm1000"
MODO_PIXELES = "pixeles"
MODOS = (MODO_NORM, MODO_PIXELES)
PREFIJO_PROMPT = ('Esta es una captura de pantalla de 1280x800 píxeles de una aplicación. '
                  'Responde SOLO con un JSON {"x": número, "y": número} con el punto '
                  'central de ')
INSTRUCCION_NORM = ('Da x e y en una escala de 0 a 1000, donde (0, 0) es la esquina '
                    'superior izquierda y (1000, 1000) la esquina inferior derecha.')
INSTRUCCION_PIXELES = ('Da x e y en píxeles de la imagen, que mide 1280 de ancho '
                       'y 800 de alto.')

# NOTA: rutas y nombres de la salida.
RUTA_CASOS = Path(__file__).resolve().parent / "casos_punteria.json"
PREFIJO_CARPETA_CORRIDA = "punteria_"
MARCA_DE_TIEMPO = "%Y%m%d_%H%M%S"
NOMBRE_RESULTADOS = "resultados.json"
SUFIJO_ANTES = "antes"
SUFIJO_DESPUES = "despues"
CARPETA_SALIDA_POR_DEFECTO = "logs"

# NOTA: códigos de salida: 0 terminó (aunque haya fallos de puntería), 1 fallo del
# script, 2 falta una variable de entorno.
CODIGO_OK = 0
CODIGO_FALLO = 1
CODIGO_FALTA_VARIABLE = 2


class ErrorModelo(Exception):
    # NOTA: fallo de la llamada al modelo; el mensaje nunca lleva cuerpo ni llave.
    pass


def variables_faltantes() -> list[str]:
    # NOTA: nombres de las variables de entorno que faltan (nunca sus valores).
    return [nombre for nombre in (VARIABLE_URL, VARIABLE_PASSWORD, VARIABLE_TOKEN,
                                 VARIABLE_API_KEY) if not os.environ.get(nombre)]


def instruccion_de_modo(modo: str) -> str:
    # NOTA: la frase que cambia según la escala en la que debe responder el modelo.
    if modo == MODO_NORM:
        return INSTRUCCION_NORM
    if modo == MODO_PIXELES:
        return INSTRUCCION_PIXELES
    raise ValueError(f"modo desconocido: {modo!r}")


def prompt_para(descripcion: str, modo: str) -> str:
    # NOTA: prompt en español tal cual lo fija el encargo, con la instrucción del modo.
    return f"{PREFIJO_PROMPT}{descripcion}. {instruccion_de_modo(modo)}"


def cuerpo_solicitud(modelo: str, prompt: str, png: bytes) -> bytes:
    # NOTA: cuerpo JSON de chat/completions con el PNG como data URL base64.
    mensaje = {"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {
            "url": PREFIJO_DATA_URL + base64.b64encode(png).decode("ascii")}}]}
    solicitud = {"model": modelo, "temperature": 0,
                 "reasoning": {"effort": ESFUERZO_RAZONAMIENTO},
                 "usage": {"include": True}, "messages": [mensaje]}
    return json.dumps(solicitud).encode("utf-8")


def _post_openrouter(api_key: str, cuerpo: bytes) -> dict:
    # NOTA: bloqueante (urllib); to_thread lo llama; sube solo el código HTTP o el tipo.
    peticion = urllib.request.Request(
        URL_OPENROUTER, data=cuerpo, method="POST",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=TOPE_LLAMADA_S) as respuesta:
            crudo = respuesta.read()
    except urllib.error.HTTPError as exc:
        # NOTA: el cuerpo puede traer eco del prompt; solo se reporta el código.
        raise ErrorModelo(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        # NOTA: la causa puede traer la URL pública; con from None no se encadena.
        raise ErrorModelo(f"red ({type(exc).__name__})") from None
    try:
        return json.loads(crudo)
    except (ValueError, UnicodeDecodeError):
        raise ErrorModelo("respuesta sin JSON válido") from None


async def preguntar_modelo(api_key: str, modelo: str, descripcion: str,
                           modo: str, png: bytes) -> dict:
    # NOTA: una llamada al modelo con visión en un hilo, con el tope de 60 s.
    cuerpo = cuerpo_solicitud(modelo, prompt_para(descripcion, modo), png)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_post_openrouter, api_key, cuerpo), TOPE_LLAMADA_S)
    except TimeoutError:
        raise ErrorModelo("tiempo agotado") from None


def texto_de_respuesta(respuesta: dict) -> str:
    # NOTA: saca choices[0].message.content; si falta, la respuesta es inesperada.
    try:
        return respuesta["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ErrorModelo("respuesta sin contenido") from None


def extraer_punto(texto: str) -> tuple[float, float]:
    # NOTA: sirve para JSON pelado y para respuestas con bloque ```json``` o prosa.
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin <= inicio:
        raise ErrorModelo("sin JSON en la respuesta")
    try:
        punto = json.loads(texto[inicio:fin + 1])
        return float(punto["x"]), float(punto["y"])
    except (ValueError, KeyError, TypeError):
        raise ErrorModelo("JSON sin x/y numéricos") from None


def a_pixeles(x: float, y: float, modo: str) -> tuple[float, float]:
    # NOTA: norm1000 escala a la pantalla; pixeles ya viene en píxeles.
    if modo == MODO_PIXELES:
        return x, y
    return (x * ANCHO_PANTALLA_PX / ESCALA_NORMALIZADA,
            y * ALTO_PANTALLA_PX / ESCALA_NORMALIZADA)


def punto_en_caja(x: float, y: float, caja: list[int]) -> bool:
    # NOTA: dentro con bordes inclusive; caja = [x1, y1, x2, y2].
    x1, y1, x2, y2 = caja
    return x1 <= x <= x2 and y1 <= y <= y2


def error_al_centro_px(x: float, y: float, caja: list[int]) -> float:
    # NOTA: distancia euclidiana del punto predicho al centro de la caja.
    x1, y1, x2, y2 = caja
    return math.hypot(x - (x1 + x2) / 2, y - (y1 + y2) / 2)


def uso_de_respuesta(respuesta: dict) -> tuple[int | None, float | None]:
    # NOTA: tokens y costo si OpenRouter los devolvió; si no, None en su lugar.
    uso = respuesta.get("usage") or {}
    try:
        tokens = int(uso["total_tokens"])
    except (KeyError, TypeError, ValueError):
        tokens = None
    try:
        costo = float(uso["cost"])
    except (KeyError, TypeError, ValueError):
        costo = None
    return tokens, costo


def registro_de_modo(caso: dict, modo: str, respuesta: dict) -> dict:
    # NOTA: registro de un modo exitoso: punto en px, dentro, error, uso y texto crudo.
    texto = texto_de_respuesta(respuesta)
    x_modelo, y_modelo = extraer_punto(texto)
    x_px, y_px = a_pixeles(x_modelo, y_modelo, modo)
    tokens, costo = uso_de_respuesta(respuesta)
    return {"caso": caso["nombre"], "modo": modo, "x_px": x_px, "y_px": y_px,
            "dentro": punto_en_caja(x_px, y_px, caso["caja"]),
            "error_px": error_al_centro_px(x_px, y_px, caso["caja"]),
            "tokens": tokens, "costo": costo, "respuesta_cruda": texto}


def registro_de_error(caso: dict, modo: str, exc: Exception) -> dict:
    # NOTA: fallo del modo con solo el tipo de error; sin cuerpos ni secretos.
    return {"caso": caso["nombre"], "modo": modo, "x_px": None, "y_px": None,
            "dentro": None, "error_px": None, "tokens": None, "costo": None,
            "respuesta_cruda": None, "error": str(exc)}


async def medir_modo(api_key: str, modelo: str, caso: dict, modo: str,
                     png: bytes) -> dict:
    # NOTA: una pregunta al modelo convertida en registro; el fallo también lo es.
    try:
        respuesta = await preguntar_modelo(api_key, modelo, caso["descripcion"],
                                           modo, png)
        return registro_de_modo(caso, modo, respuesta)
    except ErrorModelo as exc:
        return registro_de_error(caso, modo, exc)


def a_pixel_valido(valor: float, maximo_exclusivo: int) -> int:
    # NOTA: recorta al rango del clic para que una predicción extrema no rompa el caso.
    return min(max(round(valor), 0), maximo_exclusivo - 1)


async def preparar_estado(cliente: ClienteRFB, clics: list[list[int]]) -> None:
    # NOTA: los clics de preparación del caso, con pausa fija después de cada uno.
    for x, y in clics:
        await cliente.clic(x, y)
        await asyncio.sleep(PAUSA_TRAS_CLIC_S)


async def par_bgrx_png(cliente: ClienteRFB) -> tuple[bytes, bytes]:
    # NOTA: una sola captura sirve para el diff (bgrx) y para el PNG de disco.
    bgrx = await cliente.captura_bgrx()
    return bgrx, png_desde_bgrx(bgrx, cliente.ancho, cliente.alto)


def guardar_png(carpeta: Path, nombre_caso: str, sufijo: str, png: bytes) -> None:
    # NOTA: escribe <nombre>_antes.png o <nombre>_despues.png en la carpeta de la corrida.
    (carpeta / f"{nombre_caso}_{sufijo}.png").write_bytes(png)


async def clic_y_comparar(cliente: ClienteRFB, caso: dict, registro_norm: dict,
                          bgrx_antes: bytes, carpeta: Path) -> bool | None:
    # NOTA: clic real en la predicción norm1000 y diff de pantalla; None si falló el modo.
    if registro_norm.get("x_px") is None:
        return None
    x = a_pixel_valido(registro_norm["x_px"], cliente.ancho)
    y = a_pixel_valido(registro_norm["y_px"], cliente.alto)
    await cliente.clic(x, y)
    await cliente.esperar_quieta()
    bgrx_despues, png_despues = await par_bgrx_png(cliente)
    guardar_png(carpeta, caso["nombre"], SUFIJO_DESPUES, png_despues)
    return bgrx_despues != bgrx_antes


async def correr_caso(url: str, token: str, api_key: str, modelo: str,
                      caso: dict, carpeta: Path) -> list[dict]:
    # NOTA: reset + sesión RFB nueva por caso; devuelve los registros de sus dos modos.
    await reset_escritorio(url, token)
    await asyncio.sleep(ESPERA_TRAS_RESET_S)
    registros: list[dict] = []
    async with ClienteRFB.desde_entorno() as cliente:
        await preparar_estado(cliente, caso["preparar"])
        await cliente.esperar_quieta()
        bgrx_antes, png_antes = await par_bgrx_png(cliente)
        guardar_png(carpeta, caso["nombre"], SUFIJO_ANTES, png_antes)
        for modo in MODOS:
            registros.append(await medir_modo(api_key, modelo, caso, modo, png_antes))
        # NOTA: registros[0] es norm1000 porque MODOS lo pone primero: el clic usa su punto.
        cambio = await clic_y_comparar(cliente, caso, registros[0], bgrx_antes, carpeta)
        for registro in registros:
            registro["cambio_pantalla"] = cambio
    return registros


async def correr_todos(url: str, token: str, api_key: str, modelo: str,
                       casos: list[dict], carpeta: Path) -> list[dict]:
    # NOTA: caso por caso; un fallo de escritorio o de reset no tumba a los demás.
    registros: list[dict] = []
    for caso in casos:
        try:
            registros.extend(await correr_caso(url, token, api_key, modelo,
                                               caso, carpeta))
        except Exception as exc:
            print(f"caso {caso['nombre']}: falló ({type(exc).__name__})")
    return registros


def texto_de_columna(valor: bool | None) -> str:
    # NOTA: True es «sí», False es «no» y None es «-» (no se supo).
    return {True: "sí", False: "no", None: "-"}.get(valor, "-")


def imprimir_tabla(registros: list[dict]) -> None:
    # NOTA: caso · modo · dentro · error en px · cambió la pantalla.
    print(f"{'caso':<18} {'modo':<10} {'dentro':<7} {'error_px':>8} {'cambió':<8}")
    for registro in registros:
        error = (f"{registro['error_px']:.1f}"
                 if registro.get("error_px") is not None else "-")
        fila = (f"{registro['caso']:<18} {registro['modo']:<10} "
                f"{texto_de_columna(registro.get('dentro')):<7} {error:>8} "
                f"{texto_de_columna(registro.get('cambio_pantalla')):<8}")
        if registro.get("error"):
            fila += f"[{registro['error']}]"
        print(fila)


def imprimir_totales(registros: list[dict]) -> None:
    # NOTA: aciertos por modo y costo total de la corrida.
    for modo in MODOS:
        del_modo = [registro for registro in registros if registro["modo"] == modo]
        aciertos = sum(1 for registro in del_modo if registro.get("dentro"))
        print(f"{modo}: {aciertos} de {len(del_modo)} casos dentro de la caja")
    costo = sum(registro["costo"] for registro in registros
                if registro.get("costo") is not None)
    print(f"costo total: {costo:.6f}")


def crear_carpeta(base: Path) -> Path:
    # NOTA: una carpeta punteria_<AAAAMMDD_HHMMSS> nueva por corrida.
    marca = datetime.now().strftime(MARCA_DE_TIEMPO)
    carpeta = base / f"{PREFIJO_CARPETA_CORRIDA}{marca}"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def cargar_casos(ruta: Path) -> list[dict]:
    # NOTA: lee la lista de casos; si no hay casos, no hay nada que medir.
    with ruta.open(encoding="utf-8") as archivo:
        casos = json.load(archivo)
    if not isinstance(casos, list) or not casos:
        raise ValueError("el archivo de casos no tiene una lista con casos")
    return casos


async def _principal(modelo: str, salida: Path) -> int:
    # NOTA: orquesta la corrida: config del entorno, casos, registros y resumen.
    faltan = variables_faltantes()
    if faltan:
        for nombre in faltan:
            print(f"falta la variable de entorno {nombre}")
        return CODIGO_FALTA_VARIABLE
    carpeta = crear_carpeta(salida)
    casos = cargar_casos(RUTA_CASOS)
    registros = await correr_todos(os.environ[VARIABLE_URL], os.environ[VARIABLE_TOKEN],
                                   os.environ[VARIABLE_API_KEY], modelo, casos, carpeta)
    ruta_resultados = carpeta / NOMBRE_RESULTADOS
    ruta_resultados.write_text(json.dumps(registros, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    imprimir_tabla(registros)
    imprimir_totales(registros)
    print(f"resultados en {ruta_resultados}")
    return CODIGO_OK


def main() -> int:
    # NOTA: punto de entrada con --modelo y --salida; un fallo acaba en 1 sin secretos.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelo", default=MODELO_POR_DEFECTO,
                        help="modelo de OpenRouter con visión")
    parser.add_argument("--salida", type=Path, default=Path(CARPETA_SALIDA_POR_DEFECTO),
                        help="carpeta base de la salida")
    try:
        argumentos = parser.parse_args()
        return asyncio.run(_principal(argumentos.modelo, argumentos.salida))
    except Exception as exc:
        print(f"falló la medición: {type(exc).__name__}")
        return CODIGO_FALLO


if __name__ == "__main__":
    sys.exit(main())
