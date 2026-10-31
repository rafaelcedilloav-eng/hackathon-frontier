"""Objetivos por fase: el texto que se le da a los ojos (solo por función, sin nombres de la app)."""
from frontier_agente.tipos_agente import Intencion

# NOTA: fases que escriben en el formulario; una fase ajena es un error del llamador.
FASES_DE_ESCRIBIR = ("crear", "modificar")
SEPARADOR_PARES = "; "
PLANTILLA_PAR = "{llave}={valor}"
MENSAJE_FASE_DESCONOCIDA = "fase de escritura desconocida: {fase!r}"

# NOTA: frase compartida por responder y exportar: hoy fija el punto de partida de las fechas relativas.
FRASE_RELATIVAS = (
    "las fechas relativas («ayer», «septiembre») se cuentan desde el "
    "«Hoy» que muestra la aplicación"
)

# NOTA: cómo llenar el formulario, por función y sin nombres de la app: listas con clic
# (elegir_opcion), Tab entre campos de texto, y un aviso de guardado ya vale como guardado.
GUIA_DE_ESCRITURA = (
    "Guía de escritura: un campo de lista desplegable no se escribe; abre la lista y "
    "haz clic en la opción que corresponde al valor pedido, declarando en la acción "
    "funcion elegir_opcion y en texto el valor elegido. "
    "Para pasar de un campo de texto al siguiente puedes usar la tecla Tab. "
    "Si tras guardar el formulario sigue abierto pero aparece un aviso de guardado o "
    "de aplicado, eso cuenta como guardado: no lo guardes otra vez y responde terminar."
)


def pares_de_texto(diccionario: dict) -> str:
    # NOTA: cada par llave=valor separado por «; »; así se nombra el registro en los objetivos.
    return SEPARADOR_PARES.join(
        PLANTILLA_PAR.format(llave=llave, valor=valor) for llave, valor in diccionario.items()
    )


def frase_de_busqueda(intencion: Intencion) -> str:
    # NOTA: arma la orden de filtrar solo con lo que hay (datos y filtros de la
    # búsqueda); sin nada de nada, la frase entera se omite.
    partes = []
    if intencion.identificador:
        partes.append("datos de búsqueda: " + pares_de_texto(intencion.identificador))
    if intencion.filtros:
        partes.append("filtros: " + pares_de_texto(intencion.filtros))
    if not partes:
        return ""
    return (
        "Usa el filtro o la búsqueda de la aplicación para hallar el registro o la lista: "
        + SEPARADOR_PARES.join(partes) + ". "
    )


def objetivo_resolver(intencion: Intencion) -> str:
    # NOTA: fase resolver: solo buscar y leer resultados; la prohibición de tocar va explícita.
    return (
        "Estás en la fase de resolver. "
        f"Busca con el filtro de la aplicación el registro de {intencion.entidad} "
        f"cuyos datos son: {pares_de_texto(intencion.identificador)}. "
        "Mientras buscas, no crees, modifiques ni guardes nada. "
        "Cuando veas el resultado, responde con la acción leer y en lectura un objeto "
        "con la clave candidatos: una lista con cada fila coincidente visible, donde cada fila "
        "trae identificador (el documento, NIT, ID o código visible de la fila) y campos "
        "(las parejas llave-valor que se ven en la fila), y la clave hay_mas_paginas con true o false. "
        'Si la aplicación dice que no hay resultados, responde lectura con {"candidatos": []}.'
    )


def objetivo_escribir(intencion: Intencion, fase: str) -> str:
    # NOTA: fase de escritura (crear o modificar): valores exactos de la tarea y un solo guardado.
    if fase not in FASES_DE_ESCRIBIR:
        raise ValueError(MENSAJE_FASE_DESCONOCIDA.format(fase=fase))
    if fase == "crear":
        apertura = (
            f"Abre el formulario de nuevo registro de {intencion.entidad} y escribe en cada "
            f"campo exactamente estos valores: {pares_de_texto(intencion.campos)}."
        )
    else:
        apertura = (
            f"Abre el registro de {intencion.entidad} hallado por el identificador: "
            f"{pares_de_texto(intencion.identificador)}, y cambia solo estos campos: "
            f"{pares_de_texto(intencion.campos)}."
        )
    return (
        f"Estás en la fase de {fase}. {apertura} {GUIA_DE_ESCRITURA} "
        "Pulsa el control de guardar una sola vez y, al ver la confirmación "
        "o el registro ya guardado, responde con la acción terminar."
    )


def objetivo_verificar(intencion: Intencion) -> str:
    # NOTA: fase verificar: releer sin decir los valores esperados, para que el modelo lea y no copie.
    llaves = ", ".join(intencion.campos)
    return (
        "Estás en la fase de verificar. "
        f"Busca el registro de {intencion.entidad} por el identificador: "
        f"{pares_de_texto(intencion.identificador)}, ábrelo y responde con la acción leer "
        "y en lectura un objeto con el valor que se ve en el registro para cada una "
        f"de estas llaves y solo esas: {llaves}."
    )


def objetivo_responder(intencion: Intencion) -> str:
    # NOTA: fase responder: filtra, lee el dato que pide la pregunta y lo devuelve
    # como texto en lectura; para contar va la receta en orden (hallazgo E3:
    # paginar en círculos agotaba los pasos), con el total de la app primero.
    return (
        "Estás en la fase de responder. "
        "La aplicación muestra la fecha de hoy y "
        f"{FRASE_RELATIVAS}. "
        f"Responde a esta pregunta: {intencion.pregunta} "
        f"{frase_de_busqueda(intencion)}"
        "Si la pregunta pide contar, sigue esta receta en orden: "
        "primero aplica los filtros con el buscador de la aplicación y ejecuta la búsqueda; "
        "si la aplicación muestra un total de resultados (junto a la lista o en la "
        "paginación), responde con ese número; si no lo muestra, cuenta página por "
        "página: cuenta las filas visibles de la página en la que estás ANTES de avanzar "
        "(puedes nombrar los códigos visibles en tu razon para no perderte), pasa a la "
        "siguiente y repite hasta la última, y responde con la suma; si llegaste a una "
        "página sin haber contado la anterior, vuelve a la que falta, cuéntala y sigue "
        "desde ahí; lo prohibido es repetir páginas ya contadas, no recuperar una que te "
        "saltaste. Nunca cuentes de una sola mirada. "
        "Tu conteo parcial vive en tu razon: termina cada razon con "
        '"CONTEO: <número acumulado> (páginas contadas: <lista>)" y confía en él al '
        "llegar a una página nueva: no re-cuentes una página que tu razon anterior ya "
        "contó. Para pasar de página usa los controles de paginación de la lista "
        "(anterior/siguiente), nunca las filas: una fila abre su detalle y te saca de "
        "la lista. "
        "Si la pregunta pide un dato de un registro, abre ese registro y lee ese dato en él. "
        "Cuando tengas la respuesta con certeza, responde con la acción leer y "
        'lectura = {"respuesta": "<texto exacto>"}; con un solo dato va ese dato y '
        'con dos datos, "dato 1; dato 2" en el orden en que se preguntaron. '
        "Si no puedes responder con certeza, responde con la acción fallar y la razón."
    )


def objetivo_exportar(intencion: Intencion) -> str:
    # NOTA: fase exportar (E4): el reporte ES la lista de la entidad de la tarea;
    # se filtra con su buscador y se exporta desde esa misma lista, sin menús de «reportes».
    if intencion.filtros:
        aplicacion = (
            "aplica estos filtros con su buscador: "
            + pares_de_texto(intencion.filtros) + "; "
        )
    else:
        aplicacion = ""
    return (
        "Estás en la fase de exportar. "
        "El reporte es la lista de los registros de la entidad de esta tarea, no un menú aparte: "
        f"ábrela en su módulo de {intencion.entidad} sin buscar un menú de «reportes». "
        f"Cuando la tengas abierta, {aplicacion}"
        f"{FRASE_RELATIVAS}. "
        "Pulsa el control de exportar de esa misma lista (en la acción, funcion exportar) "
        "una sola vez y, al ver el archivo generado, descargado o confirmado, "
        "responde con la acción terminar. "
        "Si algo lo impide, responde con la acción fallar y la razón."
    )
