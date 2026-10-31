"""Valida la intención que propone el modelo contra la tarea; nunca lanza."""
from frontier_agente.texto import (
    aparece_en_tarea,
    es_letra_de_valor,
    normalizar_clave,
    palabras_de,
)
from frontier_agente.tipos_agente import TIPOS_INTENCION, Intencion

# NOTA: verbos que convierten la tarea en destructiva; palabra completa y sin
# acentos (palabras_de es la única fuente de partir en palabras).
PALABRAS_DESTRUCTIVAS = (
    "elimina", "eliminar", "elimine", "borra", "borrar", "borre",
    "anula", "anular", "suprime", "suprimir", "destruye", "destruir",
    "vacia", "vaciar",
)
# NOTA: regla 4 del bloque 5: revertir es legítimo si la tarea pide deshacer o
# restaurar; deshacer/restaurar/revertir NO son destructivos (regla 3 vieja).
PALABRAS_REVERTIR = ("deshacer", "restaurar", "restaura", "revertir")
# NOTA: prefijos de la misma regla: "deshac" cubre la familia des+hacer
# (deshace, deshacer), "repon" cubre reponer y "repos" cubre reposición
# (que no empieza por "repon").
PREFIJOS_REVERTIR = ("deshac", "repon", "repos")
TIPO_OTRO = "otro"
BLOQUES = ("identificador", "campos", "filtros")
# NOTA: bloques del crudo que declaran llaves de campos que no se verifican
# contra la tarea (regla 3 del bloque 5).
BLOQUES_EXENTOS = ("condicionales", "pantalla")
# NOTA: llaves que identifican univocamente a un registro; con ellas el código
# decide el identificador de un crear cuando el modelo no dio uno válido.
CLAVES_UNICAS = (
    "nit", "documento", "cedula", "id", "codigo",
    "rfc", "curp", "ruc", "dni", "rut", "identificacion",
)
# NOTA: numeración inicial de los elementos de una lista aplanada (I2.6).
PRIMERA_POSICION = 1
MENSAJE_DESTRUCTIVA = "la tarea pide una acción destructiva"
MENSAJE_TIPO_NO_SOPORTADO = "tipo de tarea no soportado"
MENSAJE_NO_ES_DICT = "la respuesta del modelo no es un objeto"


def validar_intencion(crudo: object, tarea: str) -> Intencion:
    # NOTA: nunca lanza; cualquier problema se devuelve como motivo_fallo con
    # el tipo que se pudo leer. Lo destructivo se decide antes que cualquier
    # otra regla; texto_tarea y permite_revertir se llenan siempre (regla 4).
    tipo = _leer_tipo(crudo)
    revertir = _permite_revertir(tarea)
    if _es_destructiva(tarea):
        return Intencion(
            tipo=tipo,
            peligrosa=True,
            motivo_fallo=MENSAJE_DESTRUCTIVA,
            permite_revertir=revertir,
            texto_tarea=tarea,
        )
    if tipo == TIPO_OTRO:
        return Intencion(
            tipo=TIPO_OTRO,
            motivo_fallo=_motivo_tipo_otro(crudo),
            permite_revertir=revertir,
            texto_tarea=tarea,
        )
    return _construir(crudo, tipo, tarea, revertir)


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
    # NOTA: busca cada verbo destructivo como palabra completa, sin distinguir
    # mayúsculas (palabras_de ya quita acentos y pasa a minúsculas).
    return any(
        palabra in PALABRAS_DESTRUCTIVAS for palabra in palabras_de(tarea)
    )


def _permite_revertir(tarea: str) -> bool:
    # NOTA: regla 4 del bloque 5: palabra completa para deshacer/restaurar/
    # restaura/revertir y prefijo para la familia des+hacer (deshace,
    # deshacer) y repon (reponer/reposición); "Cambia el teléfono a 302" no
    # trae ninguna → False.
    for palabra in palabras_de(tarea):
        if palabra in PALABRAS_REVERTIR:
            return True
        if any(palabra.startswith(prefijo) for prefijo in PREFIJOS_REVERTIR):
            return True
    return False


def _construir(
    crudo: dict[str, object], tipo: str, tarea: str, revertir: bool
) -> Intencion:
    # NOTA: valida la estructura (con el aplanado de compuestos), que cada
    # valor venga de la tarea y las reglas por tipo; devuelve la intención
    # final o el motivo del fallo, siempre con texto_tarea y permite_revertir.
    bloques = []
    for nombre_bloque in BLOQUES:
        bloque, motivo = _leer_diccionario(crudo.get(nombre_bloque))
        if motivo:
            return _fallida(tipo, motivo, revertir, tarea)
        bloques.append(bloque)
    identificador, campos, filtros = bloques
    exentas = _llaves_exentas(crudo, campos)
    motivo = _revisar_valores_en_tarea(identificador, campos, filtros, exentas, tarea)
    if motivo:
        return _fallida(tipo, motivo, revertir, tarea)
    return _aplicar_reglas(
        crudo, tipo, identificador, campos, filtros, exentas, revertir, tarea
    )


def _fallida(tipo: str, motivo: str, revertir: bool, tarea: str) -> Intencion:
    # NOTA: intención inválida: se conservan el tipo, revertir y el texto de la
    # tarea, y el motivo nombra el problema (los textos son los del bloque 3).
    return Intencion(
        tipo=tipo,
        motivo_fallo=motivo,
        permite_revertir=revertir,
        texto_tarea=tarea,
    )


def _leer_diccionario(valor: object) -> tuple[dict[str, str], str]:
    # NOTA: normaliza un bloque a {llave_texto: valor_texto}; los valores
    # compuestos (dict/list) se aplanan (regla 1 del bloque 5); vacío si falta
    # y motivo si no es diccionario, la llave no es texto o el valor no es
    # texto/número.
    if valor is None:
        return {}, ""
    if not isinstance(valor, dict):
        return {}, "un bloque de la intención no es un objeto"
    resultado = {}
    for llave, contenido in valor.items():
        if not isinstance(llave, str):
            return {}, "una llave no es texto"
        pares, motivo = _aplanar_valor(llave, contenido)
        if motivo:
            return {}, motivo
        resultado.update(pares)
    return resultado, ""


def _aplanar_valor(llave: str, contenido: object) -> tuple[dict[str, str], str]:
    # NOTA: regla 1 del bloque 5: un valor dict se aplana en pares
    # "<padre> <subllave>" (subllave con normalizar_clave) y una lista de
    # textos en pares "<llave> <n>" (n desde 1); cada subvalor se verifica
    # igual que un valor normal.
    if isinstance(contenido, dict):
        return _aplanar_dict(llave, contenido)
    if isinstance(contenido, list):
        return _aplanar_lista(llave, contenido)
    texto = _texto_o_none(contenido)
    if texto is None:
        return {}, f"el valor de {llave} no es texto ni número"
    return {llave: texto}, ""


def _aplanar_dict(
    llave: str, contenido: dict[object, object]
) -> tuple[dict[str, str], str]:
    # NOTA: subllaves de texto y subvalores texto/número; la llave final es
    # "<padre> <subllave normalizada>" (I2.5: "acudiente documento").
    pares = {}
    for subllave, subvalor in contenido.items():
        if not isinstance(subllave, str):
            return {}, f"una llave de {llave} no es texto"
        texto = _texto_o_none(subvalor)
        if texto is None:
            return {}, f"el valor de {llave} no es texto ni número"
        pares[f"{llave} {normalizar_clave(subllave)}"] = texto
    return pares, ""


def _aplanar_lista(llave: str, contenido: list) -> tuple[dict[str, str], str]:
    # NOTA: elementos texto/número; la llave final es "<llave> <posición>"
    # desde PRIMERA_POSICION (I2.6: "telefonos 1", "telefonos 2").
    pares = {}
    for posicion, elemento in enumerate(contenido, PRIMERA_POSICION):
        texto = _texto_o_none(elemento)
        if texto is None:
            return {}, f"el valor de {llave} no es texto ni número"
        pares[f"{llave} {posicion}"] = texto
    return pares, ""


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


def _llaves_exentas(
    crudo: dict[str, object], campos: dict[str, str]
) -> tuple[str, ...]:
    # NOTA: regla 3 del bloque 5: condicionales y pantalla; solo cuentan las
    # llaves que existen en campos, únicas y en el orden dado; un bloque que
    # no es lista (o elementos que no son texto) se ignora: no abre la puerta
    # a valores sin verificar, a lo sumo hace fallar la intención después.
    exentas: list[str] = []
    for bloque in BLOQUES_EXENTOS:
        for llave in _lista_de_textos(crudo.get(bloque)):
            clave = _llave_existente(llave, campos)
            if clave is not None and clave not in exentas:
                exentas.append(clave)
    return tuple(exentas)


def _lista_de_textos(valor: object) -> list[str]:
    # NOTA: solo listas/tuplas de textos; todo lo demás se ignora.
    if not isinstance(valor, (list, tuple)):
        return []
    return [elemento for elemento in valor if isinstance(elemento, str)]


def _llave_existente(llave: str, campos: dict[str, str]) -> str | None:
    # NOTA: devuelve la llave real de campos que corresponde (exacta o igual
    # sin acentos), para que el exento coincida con la llave que el juez
    # comparará después; None si la llave no existe (se ignora).
    if llave in campos:
        return llave
    objetivo = normalizar_clave(llave)
    for clave in campos:
        if normalizar_clave(clave) == objetivo:
            return clave
    return None


def _revisar_valores_en_tarea(
    identificador: dict[str, str],
    campos: dict[str, str],
    filtros: dict[str, str],
    exentas: tuple[str, ...],
    tarea: str,
) -> str:
    # NOTA: regla 2 del bloque 5: los campos se revisan primero (la inyección
    # vive ahí y el motivo debe nombrarla, I2.7) y pasan con es_letra_de_valor
    # (literal o raíz) o con su llave exenta; identificador y filtros siguen
    # después con la comprobación literal (regla 5: no se debilitan); si un
    # valor no pasa, el motivo lo nombra.
    for llave, valor in campos.items():
        if llave in exentas:
            continue
        if not es_letra_de_valor(valor, tarea):
            return f"el valor {valor} no está en la tarea"
    for bloque in (identificador, filtros):
        for valor in bloque.values():
            if not aparece_en_tarea(valor, tarea):
                return f"el valor {valor} no está en la tarea"
    return ""


def _aplicar_reglas(
    crudo: dict[str, object],
    tipo: str,
    identificador: dict[str, str],
    campos: dict[str, str],
    filtros: dict[str, str],
    exentas: tuple[str, ...],
    revertir: bool,
    tarea: str,
) -> Intencion:
    # NOTA: reglas por tipo; cada rama produce la intención final o el motivo,
    # siempre con los exentos, permite_revertir y el texto de la tarea.
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
        campos_exentos=exentas,
        permite_revertir=revertir,
        texto_tarea=tarea,
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
