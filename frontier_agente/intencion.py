"""Valida la intención que propone el modelo contra la tarea; nunca lanza."""
import re

from frontier_agente.texto import (
    es_texto_numerico,
    normalizar_clave,
    normalizar_valor,
    solo_digitos,
)
from frontier_agente.tipos_agente import TIPOS_INTENCION, Intencion

# NOTA: verbos que convierten la tarea en destructiva; se buscan como palabra completa.
PALABRAS_DESTRUCTIVAS = (
    "elimina", "eliminar", "elimine", "borra", "borrar", "borre",
    "anula", "anular", "suprime", "suprimir", "destruye", "destruir",
    "vacía", "vaciar",
)
TIPO_OTRO = "otro"
# NOTA: llaves que identifican univocamente a un registro; con ellas el código
# decide el identificador de un crear cuando el modelo no dio uno válido.
CLAVES_UNICAS = (
    "nit", "documento", "cedula", "id", "codigo",
    "rfc", "curp", "ruc", "dni", "rut", "identificacion",
)
MENSAJE_DESTRUCTIVA = "la tarea pide una acción destructiva"
MENSAJE_TIPO_NO_SOPORTADO = "tipo de tarea no soportado"
MENSAJE_NO_ES_DICT = "la respuesta del modelo no es un objeto"
PALABRA_COMPLETA = r"\b{}\b"


def validar_intencion(crudo: object, tarea: str) -> Intencion:
    # NOTA: nunca lanza; cualquier problema se devuelve como motivo_fallo con el
    # tipo que se pudo leer. Lo destructivo se decide antes que cualquier otra regla.
    tipo = _leer_tipo(crudo)
    if _es_destructiva(tarea):
        return Intencion(tipo=tipo, peligrosa=True, motivo_fallo=MENSAJE_DESTRUCTIVA)
    if tipo == TIPO_OTRO:
        return Intencion(tipo=TIPO_OTRO, motivo_fallo=_motivo_tipo_otro(crudo))
    return _construir(crudo, tipo, tarea)


def _leer_tipo(crudo: object) -> str:
    # NOTA: única comprobación de TIPOS_INTENCION; devuelve el tipo legible o "otro".
    if isinstance(crudo, dict) and crudo.get("tipo") in TIPOS_INTENCION:
        return str(crudo["tipo"])
    return TIPO_OTRO


def _motivo_tipo_otro(crudo: object) -> str:
    # NOTA: distingue el "otro" de verdad (regla 6) de una respuesta que no es
    # objeto o con un tipo inventado (regla 1).
    if not isinstance(crudo, dict):
        return MENSAJE_NO_ES_DICT
    if crudo.get("tipo") == TIPO_OTRO:
        return MENSAJE_TIPO_NO_SOPORTADO
    return f"el tipo {crudo.get('tipo')!r} no es válido"


def _es_destructiva(tarea: str) -> bool:
    # NOTA: busca cada verbo destructivo como palabra completa, sin distinguir mayúsculas.
    tarea_min = tarea.casefold()
    return any(
        re.search(PALABRA_COMPLETA.format(re.escape(verbo)), tarea_min)
        for verbo in PALABRAS_DESTRUCTIVAS
    )


def _construir(crudo: dict[str, object], tipo: str, tarea: str) -> Intencion:
    # NOTA: valida la estructura, que cada valor venga de la tarea y las reglas
    # por tipo; devuelve la intención final o el motivo del fallo.
    bloques = []
    for nombre_bloque in ("identificador", "campos", "filtros"):
        bloque, motivo = _leer_diccionario(crudo.get(nombre_bloque))
        if motivo:
            return Intencion(tipo=tipo, motivo_fallo=motivo)
        bloques.append(bloque)
    motivo = _revisar_valores_en_tarea(bloques, tarea)
    if motivo:
        return Intencion(tipo=tipo, motivo_fallo=motivo)
    return _aplicar_reglas(crudo, tipo, *bloques)


def _leer_diccionario(valor: object) -> tuple[dict[str, str], str]:
    # NOTA: normaliza un bloque a {llave_texto: valor_texto}; vacío si falta
    # y motivo si no es diccionario, la llave no es texto o el valor no es texto/número.
    if valor is None:
        return {}, ""
    if not isinstance(valor, dict):
        return {}, "un bloque de la intención no es un objeto"
    resultado = {}
    for llave, contenido in valor.items():
        if not isinstance(llave, str):
            return {}, "una llave no es texto"
        contenido_texto = _texto_o_none(contenido)
        if contenido_texto is None:
            return {}, f"el valor de {llave} no es texto ni número"
        resultado[llave] = contenido_texto
    return resultado, ""


def _texto_o_none(valor: object) -> str | None:
    # NOTA: acepta texto o número (sin decimales sobrantes: 901234567.0 -> "901234567");
    # cualquier otro tipo se reporta como error devolviendo None.
    if isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        if float(valor).is_integer():
            return str(int(valor))
        return str(valor)
    return None


def _revisar_valores_en_tarea(bloques: list[dict[str, str]], tarea: str) -> str:
    # NOTA: cada valor de identificador/campos/filtros debe aparecer en la tarea,
    # como texto normalizado o, si es numérico, por sus dígitos.
    for bloque in bloques:
        for valor in bloque.values():
            if not _valor_en_tarea(valor, tarea):
                return f"el valor {valor} no está en la tarea"
    return ""


def _valor_en_tarea(valor: str, tarea: str) -> bool:
    # NOTA: el valor debe ser subcadena de la tarea normalizada o, si es numérico,
    # de sus dígitos (así "315 765 4321" aparece en "...3157654321").
    if normalizar_valor(valor) in normalizar_valor(tarea):
        return True
    if es_texto_numerico(valor):
        return solo_digitos(valor) in solo_digitos(tarea)
    return False


def _aplicar_reglas(
    crudo: dict[str, object],
    tipo: str,
    identificador: dict[str, str],
    campos: dict[str, str],
    filtros: dict[str, str],
) -> Intencion:
    # NOTA: reglas por tipo; cada rama produce la intención final o el motivo.
    entidad = crudo.get("entidad") if isinstance(crudo.get("entidad"), str) else ""
    pregunta = crudo.get("pregunta") if isinstance(crudo.get("pregunta"), str) else ""
    if tipo == "crear":
        identificador, motivo = _regla_crear(identificador, campos)
    elif tipo == "modificar":
        motivo = _regla_modificar(identificador, campos)
    elif tipo == "consultar":
        motivo = "" if pregunta else "la consulta no trae pregunta"
    elif tipo == "exportar":
        motivo = "" if filtros else "la exportación no trae filtros"
    else:
        motivo = MENSAJE_TIPO_NO_SOPORTADO
    return Intencion(
        tipo=tipo,
        entidad=entidad,
        identificador=identificador,
        campos=campos,
        pregunta=pregunta,
        filtros=filtros,
        motivo_fallo=motivo,
    )


def _regla_crear(
    identificador: dict[str, str], campos: dict[str, str]
) -> tuple[dict[str, str], str]:
    # NOTA: crear exige campos; el identificador lo decide el código de forma
    # estable y un identificador raro del modelo nunca lo hace fallar: primero
    # manda el primer campo con clave única (nit, documento...) y el modelo no
    # puede cambiarlo; si no hay, las llaves del modelo que estén en campos;
    # y si tampoco queda ninguna, el primer par de campos.
    if not campos:
        return identificador, "la tarea no dice qué crear"
    por_clave_unica = _primer_campo_con_clave_unica(campos)
    if por_clave_unica is not None:
        return por_clave_unica, ""
    sobrevivientes = {
        llave: valor for llave, valor in identificador.items() if llave in campos
    }
    if sobrevivientes:
        return sobrevivientes, ""
    primer_llave, primer_valor = next(iter(campos.items()))
    return {primer_llave: primer_valor}, ""


def _primer_campo_con_clave_unica(campos: dict[str, str]) -> dict[str, str] | None:
    # NOTA: el primer par de campos cuya llave normalizada sea una de
    # CLAVES_UNICAS; None si ningún campo la tiene.
    for llave, valor in campos.items():
        if normalizar_clave(llave) in CLAVES_UNICAS:
            return {llave: valor}
    return None


def _regla_modificar(identificador: dict[str, str], campos: dict[str, str]) -> str:
    # NOTA: modificar necesita decir a qué registro y qué cambiar.
    if not identificador:
        return "no dice qué registro modificar"
    if not campos:
        return "no dice qué cambiar"
    return ""
