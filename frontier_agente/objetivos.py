"""Objetivos por fase: el texto que se le da a los ojos (solo por función, sin nombres de la app)."""
from frontier_agente.tipos_agente import Intencion

# NOTA: fases que escriben en el formulario; una fase ajena es un error del llamador.
FASES_DE_ESCRIBIR = ("crear", "modificar")
SEPARADOR_PARES = "; "
PLANTILLA_PAR = "{llave}={valor}"
MENSAJE_FASE_DESCONOCIDA = "fase de escritura desconocida: {fase!r}"

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
