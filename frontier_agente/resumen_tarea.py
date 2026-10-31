"""Arma el resumen en texto de cómo terminó una tarea."""
from frontier_agente.tipos_agente import ESTADO_TERMINADA, Intencion, ResultadoTarea

# NOTA: primeras líneas por tipo de tarea y prefijos fijos del formato del resumen.
LINEA_CREAR = "Creé el registro verificado"
LINEA_MODIFICAR = "Modifiqué el registro verificado"
LINEA_CONSULTAR = "Respondí la consulta"
LINEA_EXPORTAR = "Exporté el reporte"
LINEA_GENERICA = "Tarea terminada"
PREFIJO_RESPUESTA = "respuesta: "
PREFIJO_VERIFICADO = "Verificado releyendo: "
PREFIJO_NOTA = "Nota: "
PREFIJO_CANDIDATO = "- "
LINEA_CANDIDATOS = "Candidatos:"
SANGRIA_CAMPOS = "  "
SEPARADOR_RESPUESTA = "; "
SEPARADOR_CAMPOS = ", "
SEPARADOR_PARES = "="
MENSAJE_NO_COMPLETADA = "No pude completar la tarea: "


def armar_resumen(resultado: ResultadoTarea, intencion: Intencion | None) -> tuple[str, str]:
    # NOTA: el resumen cambia según el estado; las notas van al final. Nunca
    # quedan saltos de línea al final ni líneas formadas solo por espacios,
    # y ningún valor no textual revienta: todo pasa por _a_texto.
    if resultado.estado == ESTADO_TERMINADA:
        lineas = _lineas_terminada(resultado, intencion)
    else:
        lineas = _lineas_fallida(resultado)
    lineas.extend(_lineas_de_notas(resultado.notas))
    lineas = [linea for linea in lineas if linea.strip() != ""]
    return resultado.estado, "\n".join(lineas).rstrip()


def _a_texto(valor: object) -> str:
    # NOTA: único punto del módulo donde un valor no textual se convierte a
    # texto (números en la respuesta o en campos, identificadores raros).
    return str(valor)


def _lineas_terminada(resultado: ResultadoTarea, intencion: Intencion | None) -> list[str]:
    # NOTA: la respuesta (si la hay) va primera, antes de cualquier otro texto
    # (decisión del director); después la línea de lo hecho y, si hay, lo verificado.
    lineas = []
    valores_respuesta = _valores_de_respuesta(resultado.respuesta)
    if valores_respuesta:
        lineas.append(PREFIJO_RESPUESTA + SEPARADOR_RESPUESTA.join(valores_respuesta))
    lineas.append(_linea_lo_hecho(intencion))
    lineas.extend(_lineas_verificados(resultado.campos_verificados))
    return lineas


def _valores_de_respuesta(respuesta: object) -> list[str]:
    # NOTA: la respuesta llega como tupla; un valor suelto (incluso un número)
    # se envuelve en una sola columna y cada elemento pasa por _a_texto.
    if isinstance(respuesta, (tuple, list)):
        return [_a_texto(valor) for valor in respuesta]
    if respuesta:
        return [_a_texto(respuesta)]
    return []


def _linea_lo_hecho(intencion: Intencion | None) -> str:
    # NOTA: qué se hizo, según el tipo de tarea; sin intención es genérica.
    if intencion is None:
        return LINEA_GENERICA
    return {
        "crear": LINEA_CREAR,
        "modificar": LINEA_MODIFICAR,
        "consultar": LINEA_CONSULTAR,
        "exportar": LINEA_EXPORTAR,
    }.get(intencion.tipo, LINEA_GENERICA)


def _lineas_verificados(campos_verificados: object) -> list[str]:
    # NOTA: la línea "Verificado releyendo:" solo existe si hay campos
    # verificados; un bloque que no es dict no produce línea.
    if not isinstance(campos_verificados, dict) or not campos_verificados:
        return []
    pares = SEPARADOR_RESPUESTA.join(_pares_de_campos(campos_verificados))
    return [PREFIJO_VERIFICADO + pares]


def _lineas_fallida(resultado: ResultadoTarea) -> list[str]:
    # NOTA: la fallida nunca muestra respuesta; lista los candidatos si los hay
    # y un candidato sin campos no emite línea de sangría (R10).
    lineas = [MENSAJE_NO_COMPLETADA + _a_texto(resultado.motivo)]
    lineas.extend(_lineas_de_candidatos(resultado.candidatos))
    return lineas


def _lineas_de_candidatos(candidatos: object) -> list[str]:
    # NOTA: una línea por candidato y otra con sus campos; algo que no es
    # tuple/lista no produce líneas y el identificador pasa por _a_texto.
    if not isinstance(candidatos, (tuple, list)) or not candidatos:
        return []
    lineas = [LINEA_CANDIDATOS]
    for candidato in candidatos:
        identificador = getattr(candidato, "identificador", candidato)
        lineas.append(PREFIJO_CANDIDATO + _a_texto(identificador))
        campos = getattr(candidato, "campos", None)
        if isinstance(campos, dict) and campos:
            lineas.append(SANGRIA_CAMPOS + _campos_del_candidato(campos))
    return lineas


def _lineas_de_notas(notas: object) -> list[str]:
    # NOTA: una línea por nota; lo que no es tuple/lista no produce líneas.
    if not isinstance(notas, (tuple, list)):
        return []
    return [PREFIJO_NOTA + _a_texto(nota) for nota in notas]


def _campos_del_candidato(campos: dict[str, str]) -> str:
    # NOTA: los campos del candidato en una línea: campo=valor, campo=valor.
    return SEPARADOR_CAMPOS.join(_pares_de_campos(campos))


def _pares_de_campos(campos: dict[str, str]) -> list[str]:
    # NOTA: convierte un diccionario en pares "campo=valor" en su orden
    # original; llaves y valores no textuales pasan por _a_texto.
    return [
        SEPARADOR_PARES.join((_a_texto(nombre), _a_texto(valor)))
        for nombre, valor in campos.items()
    ]
