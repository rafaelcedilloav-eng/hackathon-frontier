"""El guarda vigila cada acción antes de ejecutarse y registra el resultado."""
import math

from frontier_agente.texto import valores_iguales
from frontier_agente.tipos_agente import (
    FUNCIONES_CONTROL,
    Accion,
    EstadoLazo,
    Intencion,
    Veredicto,
)

# NOTA: límites del lazo y del clic; las coordenadas van en escala 0-1000.
MAX_PASOS_TOTAL = 40
LIMITE_COORDENADA = 1000
# NOTA: tras un guardado, un clic dentro de esta distancia euclídea (escala
# 0-1000) de la posición donde se guardó se toma por un doble guardado.
DISTANCIA_SEGUNDO_GUARDADO = 30
MOTIVO_CLIC_REPETIDO = "ya se guardó una vez: clic repetido en el control de guardar"
COORDENADAS_GUARDADAS = 2
FASES_DE_GUARDAR = ("crear", "modificar")
TECLAS_SIEMPRE = ("Tab", "Esc")
TECLAS_ENTER = "Enter"
FUNCION_GUARDAR = "guardar"
FUNCION_ELEGIR_OPCION = "elegir_opcion"
FUNCIONES_DE_ENTER = ("buscar", FUNCION_GUARDAR)


def evaluar_accion(accion: Accion, intencion: Intencion, estado: EstadoLazo) -> Veredicto:
    # NOTA: reglas en orden fijo; la primera que bloquea decide el veredicto
    # (cada regla devuelve permitida=True si no le toca bloquear).
    reglas = (
        _regla_intencion(intencion),
        _regla_pasos(estado),
        _regla_coordenadas(accion),
        _regla_funcion(accion),
        _regla_eliminar(accion),
        _regla_texto_de_la_tarea(accion, intencion),
        _regla_clic_repetido(accion, estado),
        _regla_guardar(accion, intencion, estado),
        _regla_tecla(accion),
    )
    for veredicto in reglas:
        if not veredicto.permitida:
            return veredicto
    return Veredicto(permitida=True)


def _regla_intencion(intencion: Intencion) -> Veredicto:
    # NOTA: una intención peligrosa o con fallo bloquea todo antes que cualquier otra regla.
    if intencion.peligrosa or intencion.motivo_fallo:
        return Veredicto(
            permitida=False,
            motivo=intencion.motivo_fallo or "la tarea pide una acción destructiva",
        )
    return Veredicto(permitida=True)


def _regla_pasos(estado: EstadoLazo) -> Veredicto:
    # NOTA: el lazo no puede pasar del tope de pasos.
    if estado.pasos >= MAX_PASOS_TOTAL:
        return Veredicto(permitida=False, motivo="tope de pasos alcanzado")
    return Veredicto(permitida=True)


def _regla_coordenadas(accion: Accion) -> Veredicto:
    # NOTA: se revisan los clics y también los escribir con con_clic=True
    # (escribir con posición primero hace clic); x e y deben caer en 0-1000.
    es_clic = accion.tipo == "clic"
    es_escribir_posicionado = accion.tipo == "escribir" and accion.con_clic
    if not (es_clic or es_escribir_posicionado):
        return Veredicto(permitida=True)
    en_rango = (
        0 <= accion.x <= LIMITE_COORDENADA
        and 0 <= accion.y <= LIMITE_COORDENADA
    )
    if not en_rango:
        return Veredicto(permitida=False, motivo="las coordenadas del clic están fuera de la pantalla")
    return Veredicto(permitida=True)


def _regla_funcion(accion: Accion) -> Veredicto:
    # NOTA: la función debe existir en el repertorio de controles.
    if accion.funcion not in FUNCIONES_CONTROL:
        return Veredicto(permitida=False, motivo=f"la función {accion.funcion} no existe")
    return Veredicto(permitida=True)


def _regla_eliminar(accion: Accion) -> Veredicto:
    # NOTA: eliminar está prohibido siempre, venga en clic o en tecla.
    if accion.funcion == "eliminar":
        return Veredicto(permitida=False, motivo="eliminar está prohibido")
    return Veredicto(permitida=True)


def _regla_texto_de_la_tarea(accion: Accion, intencion: Intencion) -> Veredicto:
    # NOTA: el texto debe ser un valor de la tarea (campos o identificador) tanto
    # al escribir como al elegir una opción de lista desplegable con un clic.
    es_escritura = accion.tipo == "escribir"
    es_eleccion = accion.tipo == "clic" and accion.funcion == FUNCION_ELEGIR_OPCION
    if not (es_escritura or es_eleccion):
        return Veredicto(permitida=True)
    valores_de_la_tarea = list(intencion.campos.values()) + list(intencion.identificador.values())
    if any(valores_iguales(accion.texto, valor) for valor in valores_de_la_tarea):
        return Veredicto(permitida=True)
    return Veredicto(permitida=False, motivo="el texto no está en la tarea")


def _regla_clic_repetido(accion: Accion, estado: EstadoLazo) -> Veredicto:
    # NOTA: regla 7a: cubre al modelo que vuelve a guardar sin etiquetar la
    # funcion; un clic en otro control dentro de la distancia también se
    # bloquea con el motivo claro (falso positivo aceptado y documentado).
    if accion.tipo != "clic" or estado.guardados < 1:
        return Veredicto(permitida=True)
    guardado = estado.posicion_guardado
    if len(guardado) != COORDENADAS_GUARDADAS:
        return Veredicto(permitida=True)
    if not all(isinstance(coordenada, (int, float)) for coordenada in guardado):
        return Veredicto(permitida=True)
    distancia = math.hypot(accion.x - guardado[0], accion.y - guardado[1])
    if distancia <= DISTANCIA_SEGUNDO_GUARDADO:
        return Veredicto(permitida=False, motivo=MOTIVO_CLIC_REPETIDO)
    return Veredicto(permitida=True)


def _regla_guardar(accion: Accion, intencion: Intencion, estado: EstadoLazo) -> Veredicto:
    # NOTA: la condición "clic, o tecla Enter, con funcion guardar" vive una sola
    # vez en _es_un_guardar; cualquier otra tecla con guardar se bloquea.
    if accion.funcion != FUNCION_GUARDAR:
        return Veredicto(permitida=True)
    if _es_un_guardar(accion):
        return _condiciones_de_guardado(intencion, estado)
    if accion.tipo == "tecla":
        return Veredicto(permitida=False, motivo="solo un clic o un Enter pueden guardar")
    return Veredicto(permitida=True)


def _condiciones_de_guardado(intencion: Intencion, estado: EstadoLazo) -> Veredicto:
    # NOTA: fase de guardar, primer guardado y todos los campos escritos;
    # el motivo nombra qué falla.
    if estado.fase not in FASES_DE_GUARDAR:
        return Veredicto(permitida=False, motivo="no es fase de guardar")
    if estado.guardados > 0:
        return Veredicto(permitida=False, motivo="ya se guardó una vez")
    faltan = [nombre for nombre in intencion.campos if nombre not in estado.campos_escritos]
    if faltan:
        return Veredicto(permitida=False, motivo="faltan campos: " + ", ".join(faltan))
    return Veredicto(permitida=True)


def _regla_tecla(accion: Accion) -> Veredicto:
    # NOTA: Enter solo con buscar o guardar; Tab y Esc siempre; cualquier otra tecla se bloquea.
    if accion.tipo != "tecla":
        return Veredicto(permitida=True)
    if accion.tecla in TECLAS_SIEMPRE:
        return Veredicto(permitida=True)
    if accion.tecla == TECLAS_ENTER and accion.funcion in FUNCIONES_DE_ENTER:
        return Veredicto(permitida=True)
    return Veredicto(permitida=False, motivo=f"la tecla {accion.tecla} no se permite")


def registrar_accion(accion: Accion, intencion: Intencion, estado: EstadoLazo) -> None:
    # NOTA: se llama solo tras una acción permitida; cuenta el paso y actualiza el estado.
    estado.pasos += 1
    if _declara_valor_de_campo(accion):
        _marcar_campos_escritos(accion, intencion, estado)
    if _es_un_guardar(accion):
        estado.guardados += 1
        if accion.tipo == "clic":
            estado.posicion_guardado = (accion.x, accion.y)


def _declara_valor_de_campo(accion: Accion) -> bool:
    # NOTA: una escritura y un clic de elegir_opcion declaran el valor de un
    # campo en texto; al registrarse marcan ese campo como escrito.
    if accion.tipo == "escribir":
        return True
    return accion.tipo == "clic" and accion.funcion == FUNCION_ELEGIR_OPCION


def _marcar_campos_escritos(accion: Accion, intencion: Intencion, estado: EstadoLazo) -> None:
    # NOTA: entra el nombre de todo campo (o identificador) cuyo valor coincide con lo escrito.
    pares = list(intencion.campos.items()) + list(intencion.identificador.items())
    for nombre, valor in pares:
        if valores_iguales(accion.texto, valor):
            estado.campos_escritos.add(nombre)


def _es_un_guardar(accion: Accion) -> bool:
    # NOTA: única definición de "guardar de control": clic o tecla Enter con
    # funcion guardar; la comparten la regla del guarda y el registro.
    if accion.funcion != FUNCION_GUARDAR:
        return False
    return accion.tipo == "clic" or (accion.tipo == "tecla" and accion.tecla == TECLAS_ENTER)
