"""Normalización y comparación de valores de texto: única fuente de verdad del agente."""
import re
import unicodedata

# NOTA: alfabeto y separadores que definen un "valor numérico" al comparar.
DIGITOS = "0123456789"
SEPARADORES_NUMERICOS = " .-()+,"

# NOTA: junta cualquier racha de espacios (tabuladores incluidos) en uno solo.
ESPACIOS_MULTIPLES = re.compile(r"\s+")


def normalizar_valor(texto: str) -> str:
    # NOTA: quita espacios de los bordes, junta los internos y pasa a minúsculas
    # con casefold para ignorar mayúsculas; conserva los acentos. Se fuerza a
    # texto para que una entrada rara (número, None) no rompa al que compara.
    return ESPACIOS_MULTIPLES.sub(" ", str(texto).strip()).casefold()


def normalizar_clave(texto: str) -> str:
    # NOTA: como normalizar_valor pero para llaves: sin acentos (NFKD sin marcas),
    # sin ":" y con el "_" contando como espacio. Se fuerza a texto al entrar
    # para que una llave no textual no reviente al resolutor.
    contenido = str(texto)
    sin_guiones = contenido.replace("_", " ")
    sin_dos_puntos = sin_guiones.replace(":", "")
    descompuesto = unicodedata.normalize("NFKD", normalizar_valor(sin_dos_puntos))
    return "".join(
        caracter
        for caracter in descompuesto
        if not unicodedata.combining(caracter)
    )


def solo_digitos(texto: str) -> str:
    # NOTA: se queda únicamente con los caracteres 0-9; todo lo demás se descarta.
    return "".join(caracter for caracter in str(texto) if caracter in DIGITOS)


def es_texto_numerico(texto: str) -> bool:
    # NOTA: decide si un texto es puro número con separadores y al menos un dígito;
    # lo comparten valores_iguales y la validación de valores contra la tarea,
    # para que el criterio "solo dígitos y separadores" no se duplique.
    contenido = str(texto)
    if not any(caracter in DIGITOS for caracter in contenido):
        return False
    permitidos = DIGITOS + SEPARADORES_NUMERICOS
    return all(caracter in permitidos for caracter in contenido)


def valores_iguales(texto_a: str, texto_b: str) -> bool:
    # NOTA: dos números con separadores se comparan por sus dígitos; cualquier
    # otro texto se compara normalizado (donde los acentos sí cuentan).
    if es_texto_numerico(texto_a) and es_texto_numerico(texto_b):
        return solo_digitos(texto_a) == solo_digitos(texto_b)
    return normalizar_valor(texto_a) == normalizar_valor(texto_b)
