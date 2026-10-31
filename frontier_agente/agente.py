"""El agente de punta a punta: interpreta, resuelve, escribe y verifica sobre la pantalla."""
import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import TypeAlias

from frontier_agente.errores import ErrorVNC
from frontier_agente.interprete import interpretar
from frontier_agente.juez import comparar_campos
from frontier_agente.lazo import Pantalla, VARIABLE_TRAZA, ejecutar_fase
from frontier_agente.modelo import llamar_modelo
from frontier_agente.objetivos import objetivo_escribir, objetivo_resolver, objetivo_verificar, pares_de_texto
from frontier_agente.ojos import Ojos
from frontier_agente.resolutor import resolver
from frontier_agente.resumen import depurar_resumen
from frontier_agente.resumen_tarea import armar_resumen
from frontier_agente.rfb_cliente import ClienteRFB
from frontier_agente.tipos import Escritorio
from frontier_agente.tipos_agente import (
    ESTADO_FALLIDA,
    ESTADO_TERMINADA,
    Candidato,
    EstadoLazo,
    ErrorModelo,
    Intencion,
    ResultadoFase,
    ResultadoTarea,
    RespuestaModelo,
)

logger = logging.getLogger(__name__)

# NOTA: tipos de tarea que este bloque sabe ejecutar; el resto cae en no soportado.
TIPOS_SOPORTADOS = ("crear", "modificar")
CAMPO_CANDIDATOS = "candidatos"

# NOTA: motivos fijos de las fallidas del agente (los que no salen de una fase).
MOTIVO_NO_INTERPRETE = "no pude interpretar la tarea (ErrorModelo)"
MOTIVO_TIPO_NO_SOPORTADO = "este tipo de tarea todavía no está soportado"
MOTIVO_YA_EXISTE = "ya existe un registro con ese dato"
MOTIVO_NO_ENCONTRADO = "no encontré el registro que busqué: "
MOTIVO_AMBIGUO = "hay varios registros que coinciden y la tarea no dice cuál"
MOTIVO_NO_GUARDADO = "no se guardó nada"
MOTIVO_NO_CONFIRMADO = "no pude confirmar el resultado releyendo el registro"
MOTIVO_CANDIDATOS_INVALIDOS = "la lectura de la búsqueda no trajo una lista de candidatos"
PLANTILLA_FALLA_CONEXION = "falló la conexión con el escritorio ({clase})"
PLANTILLA_ERROR_INTERNO = "error interno ({clase})"
PLANTILLA_DIFERENCIAS = "el registro no quedó como se pidió: "
PLANTILLA_DIFERENCIA = "{campo}: esperado {esperado}, leído {leido}"
SEPARADOR_DIFERENCIAS = "; "
COSTO_DESCONOCIDO = 0.0

# NOTA: traza siempre encendida en producción: carpeta por defecto si nadie la fija.
CARPETA_TRAZA_POR_DEFECTO = "logs"
PLANTILLA_TRAZA_POR_DEFECTO = "traza_{marca}"
FORMATO_MARCA_TRAZA = "%Y%m%d_%H%M%S"

# NOTA: firmas de las piezas que se inyectan (las pruebas falsifican ambas).
AbrirPantalla: TypeAlias = Callable[[Escritorio], AbstractAsyncContextManager[Pantalla]]
LlamarModelo: TypeAlias = Callable[..., Awaitable[RespuestaModelo]]


async def ejecutar_tarea(
    tarea: str,
    escritorio: Escritorio,
    *,
    abrir_pantalla: AbrirPantalla | None = None,
    llamar: LlamarModelo | None = None,
) -> tuple[str, str]:
    # NOTA: punto de entrada del servicio; todo fallo conocido termina en fallida
    # con motivo, y solo la cancelación sale sin capturarse. La pantalla la abre
    # (y la cierra) _correr con el administrador de contexto que reciba.
    abrir = abrir_pantalla or _abrir_cliente_rfb
    llamador = llamar or llamar_modelo
    try:
        _fijar_traza_por_defecto()
        estado, resumen, costo = await _correr(tarea, escritorio, abrir, llamador)
    except asyncio.CancelledError:
        raise
    except ErrorVNC as excepcion:
        motivo = PLANTILLA_FALLA_CONEXION.format(clase=type(excepcion).__name__)
        estado, resumen, costo = (*_fallida(motivo, None), COSTO_DESCONOCIDO)
    except Exception as excepcion:
        motivo = PLANTILLA_ERROR_INTERNO.format(clase=type(excepcion).__name__)
        estado, resumen, costo = (*_fallida(motivo, None), COSTO_DESCONOCIDO)
    resumen_limpio = depurar_resumen(resumen, [escritorio.password])
    logger.info("la tarea terminó %s (costo de los ojos: %.4f)", estado, costo)
    return estado, resumen_limpio


def _fijar_traza_por_defecto() -> None:
    # NOTA: en producción la traza va siempre: si AGENTE_TRAZA_DIR no está en el
    # entorno, se fija en logs/traza_<AAAAMMDD_HHMMSS> relativo a donde corre el
    # proceso; si algo falla, solo se avisa (nunca rompe la tarea).
    if os.environ.get(VARIABLE_TRAZA):
        return
    try:
        marca = time.strftime(FORMATO_MARCA_TRAZA)
        os.environ[VARIABLE_TRAZA] = os.path.join(
            CARPETA_TRAZA_POR_DEFECTO, PLANTILLA_TRAZA_POR_DEFECTO.format(marca=marca)
        )
    except Exception as excepcion:
        logger.warning("no se pudo fijar la carpeta de traza (%s)", type(excepcion).__name__)


def _abrir_cliente_rfb(escritorio: Escritorio) -> AbstractAsyncContextManager[Pantalla]:
    # NOTA: pantalla de producción; la contraseña solo vive aquí y dentro de ClienteRFB.

    @contextlib.asynccontextmanager
    async def _contexto() -> Pantalla:
        # NOTA: entrega el cliente ya conectado y la cierre queda en el async with.
        async with ClienteRFB(escritorio.url, escritorio.password) as cliente:
            yield cliente

    return _contexto()


async def _correr(
    tarea: str,
    escritorio: Escritorio,
    abrir: AbrirPantalla,
    llamar: LlamarModelo,
) -> tuple[str, str, float]:
    # NOTA: interpreta, despacha por tipo y corre las fases con la pantalla abierta.
    try:
        intencion = await interpretar(tarea, llamar)
    except ErrorModelo:
        return (*_fallida(MOTIVO_NO_INTERPRETE, None), COSTO_DESCONOCIDO)
    if intencion.peligrosa or intencion.motivo_fallo:
        return (*_fallida(intencion.motivo_fallo, intencion), COSTO_DESCONOCIDO)
    if intencion.tipo not in TIPOS_SOPORTADOS:
        return (*_fallida(MOTIVO_TIPO_NO_SOPORTADO, intencion), COSTO_DESCONOCIDO)
    async with abrir(escritorio) as pantalla:
        ojos = Ojos(llamar)
        estado = EstadoLazo()
        notas: list[str] = []
        resultado = await ejecutar_fase(
            "resolver", objetivo_resolver(intencion), intencion, pantalla, ojos, estado
        )
        notas.extend(resultado.notas)
        if resultado.tipo != "leer":
            return (*_fallida(resultado.razon, intencion, notas=notas), ojos.costo_total)
        crudos = resultado.lectura.get(CAMPO_CANDIDATOS)
        if not isinstance(crudos, list):
            return (*_fallida(MOTIVO_CANDIDATOS_INVALIDOS, intencion, notas=notas), ojos.costo_total)
        candidatos = [c for c in (_candidato_de(crudo) for crudo in crudos) if c is not None]
        if intencion.tipo == "crear":
            final = await _crear(intencion, pantalla, ojos, estado, candidatos, notas)
        else:
            final = await _modificar(intencion, pantalla, ojos, estado, candidatos, notas)
        return (*final, ojos.costo_total)


async def _crear(
    intencion: Intencion,
    pantalla: Pantalla,
    ojos: Ojos,
    estado: EstadoLazo,
    candidatos: list[Candidato],
    notas: list[str],
) -> tuple[str, str]:
    # NOTA: crear solo procede con la mesa vacía; un solo hallazgo ya es un duplicado.
    if candidatos:
        return _fallida(MOTIVO_YA_EXISTE, intencion, candidatos=candidatos, notas=notas)
    resultado = await ejecutar_fase(
        "crear", objetivo_escribir(intencion, "crear"), intencion, pantalla, ojos, estado
    )
    notas.extend(resultado.notas)
    return await _tras_escribir(intencion, pantalla, ojos, estado, resultado, notas)


async def _modificar(
    intencion: Intencion,
    pantalla: Pantalla,
    ojos: Ojos,
    estado: EstadoLazo,
    candidatos: list[Candidato],
    notas: list[str],
) -> tuple[str, str]:
    # NOTA: la regla del resolvedor: con 0 o varios candidatos no se toca nada.
    resolucion = resolver(candidatos, intencion.identificador)
    if resolucion.tipo == "ninguno":
        motivo = MOTIVO_NO_ENCONTRADO + pares_de_texto(intencion.identificador)
        return _fallida(motivo, intencion, notas=notas)
    if resolucion.tipo == "ambiguo":
        return _fallida(MOTIVO_AMBIGUO, intencion, candidatos=resolucion.candidatos, notas=notas)
    resultado = await ejecutar_fase(
        "modificar", objetivo_escribir(intencion, "modificar"), intencion, pantalla, ojos, estado
    )
    notas.extend(resultado.notas)
    return await _tras_escribir(intencion, pantalla, ojos, estado, resultado, notas)


async def _tras_escribir(
    intencion: Intencion,
    pantalla: Pantalla,
    ojos: Ojos,
    estado: EstadoLazo,
    resultado: ResultadoFase,
    notas: list[str],
) -> tuple[str, str]:
    # NOTA: la escritura fallida lleva su razón, y un terminar sin guardado no vale.
    if resultado.tipo == "fallar":
        return _fallida(resultado.razon, intencion, notas=notas)
    if estado.guardados == 0:
        return _fallida(MOTIVO_NO_GUARDADO, intencion, notas=notas)
    return await _verificar(intencion, pantalla, ojos, estado, notas)


async def _verificar(
    intencion: Intencion,
    pantalla: Pantalla,
    ojos: Ojos,
    estado: EstadoLazo,
    notas: list[str],
) -> tuple[str, str]:
    # NOTA: nadie declara terminada sin releer el registro y comparar lo que se pidió.
    resultado = await ejecutar_fase(
        "verificar", objetivo_verificar(intencion), intencion, pantalla, ojos, estado
    )
    notas.extend(resultado.notas)
    if resultado.tipo != "leer" or not resultado.lectura:
        return _fallida(MOTIVO_NO_CONFIRMADO, intencion, notas=notas)
    diferencias = comparar_campos(intencion.campos, resultado.lectura)
    if diferencias:
        return _fallida(_motivo_de_diferencias(diferencias), intencion, notas=notas)
    verificados = {
        campo: resultado.lectura[campo]
        for campo in intencion.campos
        if campo in resultado.lectura
    }
    exito = ResultadoTarea(
        estado=ESTADO_TERMINADA, campos_verificados=verificados, notas=tuple(notas)
    )
    return armar_resumen(exito, intencion)


def _fallida(
    motivo: str,
    intencion: Intencion | None,
    *,
    candidatos: tuple | list = (),
    notas: list[str] = (),
) -> tuple[str, str]:
    # NOTA: toda fallida pasa por el mismo armador de resumen, con sus candidatos y notas.
    resultado = ResultadoTarea(
        estado=ESTADO_FALLIDA,
        motivo=motivo,
        candidatos=tuple(candidatos),
        notas=tuple(notas),
    )
    return armar_resumen(resultado, intencion)


def _motivo_de_diferencias(diferencias: list) -> str:
    # NOTA: cada diferencia en una línea corta: campo, esperado y leído.
    detalle = SEPARADOR_DIFERENCIAS.join(
        PLANTILLA_DIFERENCIA.format(
            campo=diferencia.campo, esperado=diferencia.esperado, leido=diferencia.leido
        )
        for diferencia in diferencias
    )
    return PLANTILLA_DIFERENCIAS + detalle


def _candidato_de(crudo: object) -> Candidato | None:
    # NOTA: una fila de la lectura de resolver a un Candidato; lo que no es objeto se descarta.
    if not isinstance(crudo, dict):
        return None
    campos_crudos = crudo.get("campos")
    campos = (
        {str(llave): str(valor) for llave, valor in campos_crudos.items()}
        if isinstance(campos_crudos, dict)
        else {}
    )
    return Candidato(identificador=str(crudo.get("identificador", "")), campos=campos)
