"""Normalización y comparación de valores de texto: única fuente de verdad del agente."""
import re
import unicodedata

# NOTA: alfabeto y separadores que definen un "valor numérico" al comparar.
DIGITOS = "0123456789"
SEPARADORES_NUMERICOS = " .-()+,"

# NOTA: junta cualquier racha de espacios (tabuladores incluidos) en uno solo.
ESPACIOS_MULTIPLES = re.compile(r"\s+")
# NOTA: una palabra es una racha de letras (sin dígitos ni signos) tras quitar
# acentos y pasar a minúsculas; es la única forma de partir texto en palabras.
LETRAS = re.compile(r"[^\W\d_]+", re.UNICODE)
# NOTA: mínimo de letras para que una palabra cuente como raíz (tabla T2).
MINIMO_RAIZ = 5


def normalizar_valor(texto: str) -> str:
    # NOTA: quita espacios de los bordes, junta los internos y pasa a minúsculas
    # con casefold para ignorar mayúsculas; conserva los acentos. Se fuerza a
    # texto para que una entrada rara (número, None) no rompa al que compara.
    return ESPACIOS_MULTIPLES.sub(" ", str(texto).strip()).casefold()


def sin_acentos(texto: str) -> str:
    # NOTA: normalizar_valor y además sin marcas diacríticas (NFKD sin
    # combinantes); es la base para comparar raíces y palabras completas.
    descompuesto = unicodedata.normalize("NFKD", normalizar_valor(texto))
    return "".join(
        caracter
        for caracter in descompuesto
        if not unicodedata.combining(caracter)
    )


def normalizar_clave(texto: str) -> str:
    # NOTA: como normalizar_valor pero para llaves: sin acentos (vía
    # sin_acentos, única fuente), sin ":" y con el "_" contando como espacio.
    # Se fuerza a texto al entrar para que una llave no textual no reviente
    # al resolutor.
    contenido = str(texto)
    sin_guiones = contenido.replace("_", " ")
    return sin_acentos(sin_guiones.replace(":", ""))


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


def palabras_de(texto: str) -> list[str]:
    # NOTA: las palabras del texto (letras, sin acentos, minúsculas, en orden);
    # la comparten raiz_compartida y los verbos del validador de intención.
    return LETRAS.findall(sin_acentos(texto))


def _palabras_largas(texto: str) -> list[str]:
    # NOTA: solo palabras de MINIMO_RAIZ letras o más; las cortas no cuentan
    # para la raíz (siguen contando para la subcadena literal).
    return [palabra for palabra in palabras_de(texto) if len(palabra) >= MINIMO_RAIZ]


def raiz_compartida(valor: str, tarea: str) -> bool:
    # NOTA: regla decidida por el director (T2.5): palabra completa contra
    # palabra completa; una palabra del valor (5+ letras) pasa si es prefijo
    # de una palabra de la tarea o una palabra de la tarea es prefijo de
    # ella; como ambas miden 5+, la parte compartida siempre es de 5+.
    # «analista»/«análisis» no son prefijos una de la otra → False;
    # «cancelada»/«cancela» comparten 7 → True.
    palabras_valor = _palabras_largas(valor)
    if not palabras_valor:
        return False
    palabras_tarea = _palabras_largas(tarea)
    return any(
        palabra_valor.startswith(palabra_tarea)
        or palabra_tarea.startswith(palabra_valor)
        for palabra_valor in palabras_valor
        for palabra_tarea in palabras_tarea
    )


def aparece_en_tarea(valor: str, tarea: str) -> bool:
    # NOTA: comprobación literal: el valor es subcadena de la tarea normalizada
    # o, si es numérico, sus dígitos son subcadena de los dígitos de la tarea.
    # El identificador la usa SIN raíz para no debilitarse (regla 5, bloque 5).
    if normalizar_valor(valor) in normalizar_valor(tarea):
        return True
    if es_texto_numerico(valor):
        return solo_digitos(valor) in solo_digitos(tarea)
    return False


def es_letra_de_valor(valor: str, tarea: str) -> bool:
    # NOTA: el valor aparece literal en la tarea (subcadena o dígitos) o
    # comparte raíz con ella; es la regla 2 del bloque 5 para los campos,
    # que además pueden eximirse por llave (condicionales/pantalla).
    if aparece_en_tarea(valor, tarea):
        return True
    return raiz_compartida(valor, tarea)
