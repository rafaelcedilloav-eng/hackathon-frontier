"""Registro de tareas: estados visibles, vigilante de tope y candado por escritorio."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeAlias
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from frontier_agente.resumen import depurar_resumen
from frontier_agente.tipos import EN_CURSO, FALLIDA, TERMINADA, Escritorio

logger = logging.getLogger(__name__)

# NOTA: constantes de la especificación (puntos 7, 8 y 10 de la Tabla H).
TOPE_TAREA_S: float = 270.0
ESPERA_CANCELACION_S: float = 5.0
MAX_TAREAS: int = 200

# NOTA: textos literales del contrato; ninguno puede llevar un secreto.
RESUMEN_SIN_EJECUTOR: str = "Agente sin ejecutor configurado"
RESUMEN_RESULTADO_INVALIDO: str = "Resultado inválido del ejecutor"
RESUMEN_TIEMPO_AGOTADO: str = "Tiempo agotado: no se pudo confirmar el resultado"
RESUMEN_REEMPLAZADA: str = "Reemplazada por una tarea nueva en el mismo escritorio"
RESUMEN_SERVICIO_DETENIDO: str = "Servicio detenido"
PREFIJO_ERROR_INTERNO: str = "Error interno: "

# NOTA: el ejecutor se inyecta desde crear_app (punto 5); este es su tipo.
Ejecutor: TypeAlias = Callable[[str, Escritorio], Awaitable[tuple[str, str]]]


async def ejecutor_sin_configurar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
    """Ejecutor por defecto (punto 5): sin agente real, la tarea falla sin ser terminada."""
    # NOTA: ante la duda el servicio nunca responde terminada (lo que NO debe hacer).
    return (FALLIDA, RESUMEN_SIN_EJECUTOR)


class ErrorInternoDelEjecutor(Exception):
    """Copia despersonalizada del fallo del ejecutor, para logging.exception sin secretos."""


def clave_escritorio(url: str) -> str:
    """Clave del candado (punto 8): esquema y host en minúsculas y sin / final."""
    # NOTA: la contraseña no entra a la clave: dos tareas con la misma url son del mismo escritorio.
    partes = urlsplit(url)
    limpias = (
        partes.scheme.lower(),
        partes.netloc.lower(),
        partes.path.rstrip("/"),
        partes.query,
        partes.fragment,
    )
    return urlunsplit(limpias)


def _validar_resultado(resultado: object) -> tuple[str, str]:
    """Punto 5: solo vale (estado terminada|fallida, resumen str); lo demás es inválido."""
    # NOTA: cualquier duda sobre el resultado del ejecutor termina en fallida, nunca en terminada.
    es_valido = (
        isinstance(resultado, tuple)
        and len(resultado) == 2
        and resultado[0] in (TERMINADA, FALLIDA)
        and isinstance(resultado[1], str)
    )
    return (resultado[0], resultado[1]) if es_valido else (FALLIDA, RESUMEN_RESULTADO_INVALIDO)


def _registrar_excepcion(task_id: str, error: BaseException) -> None:
    """Punto 6: logging.exception del fallo, pero sin el texto original (trae secretos)."""
    # NOTA: se registra una copia propia con from None: el traceback del error original no llega al log.
    try:
        raise ErrorInternoDelEjecutor(type(error).__name__) from None
    except ErrorInternoDelEjecutor:
        logger.exception("el ejecutor falló en la tarea %s", task_id)


@dataclass
class _RegistroTarea:
    """Lo que responde GET /tasks/{id}: estado y resumen ya depurado (punto 9)."""

    estado: str = EN_CURSO
    resumen: str = ""


@dataclass
class _TareaEnCurso:
    """Tarea vigente de un escritorio, para cancelarla al llegar un reemplazo (punto 8)."""

    task_id: str
    escritorio: Escritorio
    corredor: asyncio.Task


class RegistroTareas:
    """Registro de tareas con vigilante de tope y candado (lock) por escritorio."""

    def __init__(
        self,
        ejecutar: Ejecutor | None,
        *,
        tope_tarea_s: float,
        espera_cancelacion_s: float,
        secretos_globales: list[str],
    ) -> None:
        """Guarda el ejecutor inyectado, los topes y los secretos que hay que depurar."""
        # NOTA: el ejecutor va por inyección; sin él todo falla como "sin ejecutor" (nunca terminada).
        self._ejecutar: Ejecutor = ejecutar or ejecutor_sin_configurar
        self._tope_tarea_s = tope_tarea_s
        self._espera_cancelacion_s = espera_cancelacion_s
        self._secretos_globales = [secreto for secreto in secretos_globales if secreto]
        self._registros: dict[str, _RegistroTarea] = {}
        self._en_curso: dict[str, _TareaEnCurso] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._corredores: set[asyncio.Task] = set()

    def crear_tarea(self, tarea: str, escritorio: Escritorio) -> str:
        """Registra la tarea, desaloja a la anterior del escritorio y crea su corredor."""
        # NOTA: todo síncrono, sin ningún await (punto 8): la reserva del candado ocurre dentro
        # del manejador del POST, y la cancelación a la anterior le llega tanto si corre como
        # si solo espera el turno del lock.
        task_id = uuid4().hex
        self._registros[task_id] = _RegistroTarea()
        self._recortar()
        clave = clave_escritorio(escritorio.url)
        self._locks.setdefault(clave, asyncio.Lock())
        anterior = self._en_curso.get(clave)
        if anterior is not None:
            self._desalojar_anterior(anterior)
        corredor = asyncio.create_task(self._correr(task_id, tarea, escritorio, clave))
        self._en_curso[clave] = _TareaEnCurso(task_id, escritorio, corredor)
        self._corredores.add(corredor)
        corredor.add_done_callback(self._corredores.discard)
        return task_id

    def estado_de(self, task_id: str) -> tuple[str, str] | None:
        """(estado, resumen) de la tarea, o None si ya no está en el registro (404)."""
        # NOTA: mientras corre ya tiene estado en_curso y resumen vacío (punto 4).
        registro = self._registros.get(task_id)
        return None if registro is None else (registro.estado, registro.resumen)

    async def apagar(self) -> None:
        """Punto 12: las tareas en curso quedan fallida con Servicio detenido y se cancelan."""
        # NOTA: la marca va antes del cancel; cada corredor espera a su ejecutor su propio tope.
        for en_curso in self._en_curso.values():
            self._finalizar(
                en_curso.task_id,
                FALLIDA,
                RESUMEN_SERVICIO_DETENIDO,
                en_curso.escritorio.password,
            )
        self._en_curso.clear()
        pendientes = set(self._corredores)
        for pendiente in pendientes:
            pendiente.cancel()
        if pendientes:
            await self._esperar_cierre(pendientes, "corredores al apagar")

    def _desalojar_anterior(self, anterior: _TareaEnCurso) -> None:
        """Punto 8: marca Reemplazada a la anterior y cancela a su corredor."""
        # NOTA: la marca va antes del cancel y solo pisa si seguía en_curso (H20): un estado
        # que ya escribió el tope no se sobreescribe con el reemplazo.
        self._finalizar(
            anterior.task_id, FALLIDA, RESUMEN_REEMPLAZADA, anterior.escritorio.password
        )
        anterior.corredor.cancel()

    def _recortar(self) -> None:
        """Punto 10: a lo más MAX_TAREAS registros; la más antigua se descarta (su id da 404)."""
        # NOTA: los dicts preservan el orden de inserción, así que la primera clave es la más antigua.
        while len(self._registros) > MAX_TAREAS:
            antigua = next(iter(self._registros))
            del self._registros[antigua]
            logger.debug("registro al tope: descartada la tarea más antigua %s", antigua)

    def _finalizar(self, task_id: str, estado: str, resumen: str, password_escritorio: str) -> None:
        """Escribe el estado final con el resumen depurado (punto 9), solo si sigue en_curso."""
        # NOTA: escribir solo si está en_curso hace que un resultado tardío tras el tope o el
        # reemplazo se descarte (H20): el estado queda como lo dejó el primero que lo escribió.
        registro = self._registros.get(task_id)
        if registro is None:
            logger.debug("la tarea %s ya salió del registro; no se guarda su resultado", task_id)
            return
        if registro.estado != EN_CURSO:
            logger.debug("la tarea %s ya tenía estado final; no se sobreescribe", task_id)
            return
        registro.estado = estado
        registro.resumen = depurar_resumen(resumen, [password_escritorio, *self._secretos_globales])

    def _quitar_del_candado(self, clave: str, task_id: str) -> None:
        """Libera la vigilancia del escritorio si la entrada del candado apunta a esta tarea."""
        # NOTA: si apunta a una tarea más nueva, esa ya reservó el turno y aquí no se toca.
        en_curso = self._en_curso.get(clave)
        if en_curso is not None and en_curso.task_id == task_id:
            del self._en_curso[clave]

    async def _tomar_turno(self, clave: str, task_id: str) -> bool:
        """Punto 8: espera el lock del escritorio con tope espera_cancelacion_s exacto."""
        # NOTA: si el anterior ignora la cancelación más del tope, manda el punto 7 (decisión
        # del director): esta tarea arranca igual y queda solo un warning sin secretos.
        adquisicion = asyncio.ensure_future(self._locks[clave].acquire())
        try:
            terminadas, _ = await asyncio.wait(
                {adquisicion}, timeout=self._espera_cancelacion_s
            )
        except asyncio.CancelledError:
            # NOTA: cancelado mientras esperaba el turno: se retira de la fila; si el lock le
            # llegó a ganar en el último instante, se libera aquí para no dejar el escritorio tomado.
            adquisicion.cancel()
            if adquisicion.done() and not adquisicion.cancelled():
                self._locks[clave].release()
            raise
        if adquisicion in terminadas and not adquisicion.cancelled():
            return True
        # NOTA: el tope venció sin adquirir: la tarea nueva arranca igual (punto 7) y no suelta
        # en su finally un lock que nunca tomó.
        adquisicion.cancel()
        logger.warning(
            "el escritorio anterior no liberó el candado en %s s; la tarea %s arranca igual",
            self._espera_cancelacion_s,
            task_id,
        )
        return False

    async def _correr(
        self, task_id: str, tarea: str, escritorio: Escritorio, clave: str
    ) -> None:
        """Toma el turno del escritorio y vigila al ejecutor; red de seguridad al salir."""
        # NOTA: con_lock dice si este corredor sostiene el candado: quien espera el turno y es
        # cancelado no tiene el lock y no puede soltarlo en su finally (release sin acquire lanza).
        con_lock = False
        try:
            con_lock = await self._tomar_turno(clave, task_id)
            await self._vigilar(task_id, tarea, escritorio)
        except asyncio.CancelledError:
            # NOTA: quien cancela (reemplazo o apagado) ya dejó el estado escrito antes del
            # cancel; la cancelación se propaga de verdad hacia asyncio.
            raise
        except Exception as error:
            # NOTA: red de seguridad (punto 6): cualquier fuga del vigilante deja estado final
            # fallida con el nombre de la clase, nunca la tarea en_curso para siempre.
            _registrar_excepcion(task_id, error)
            self._finalizar(
                task_id, FALLIDA, PREFIJO_ERROR_INTERNO + type(error).__name__, escritorio.password
            )
        finally:
            if con_lock:
                self._locks[clave].release()
            self._quitar_del_candado(clave, task_id)

    async def _vigilar(self, task_id: str, tarea: str, escritorio: Escritorio) -> None:
        """Punto 7: corre al ejecutor con tope y decide quién escribe el estado final."""
        # NOTA: el ejecutor va en tarea aparte para cancelarle solo a él, nunca al corredor.
        try:
            ejecucion = asyncio.ensure_future(self._ejecutar(tarea, escritorio))
        except Exception as error:
            # NOTA: un "ejecutor" que no es corrutina o que lanza al crearse se trata igual que
            # una excepción del ejecutor (punto 6): fallida con Error interno: <Clase>.
            _registrar_excepcion(task_id, error)
            self._finalizar(
                task_id, FALLIDA, PREFIJO_ERROR_INTERNO + type(error).__name__, escritorio.password
            )
            return
        ejecucion.add_done_callback(self._recoger_resultado_ejecutor)
        try:
            terminadas, _ = await asyncio.wait({ejecucion}, timeout=self._tope_tarea_s)
        except asyncio.CancelledError:
            # NOTA: cancelación externa (reemplazo o apagado): el estado lo escribió quien
            # canceló al corredor; el resultado tardío del ejecutor lo descarta el callback.
            await self._cerrar_ejecucion(ejecucion, task_id)
            raise
        if ejecucion in terminadas:
            self._guardar_resultado(task_id, ejecucion, escritorio)
            return
        # NOTA: tope agotado: se marca ANTES de esperar el cierre, así el servicio responde
        # aunque el ejecutor ignore la cancelación (H21); su resultado tardío se descarta (H20).
        self._finalizar(task_id, FALLIDA, RESUMEN_TIEMPO_AGOTADO, escritorio.password)
        await self._cerrar_ejecucion(ejecucion, task_id)

    async def _cerrar_ejecucion(self, ejecucion: asyncio.Future, task_id: str) -> None:
        """Cancela al ejecutor y espera que termine de cerrarse con tope (puntos 7 y 8)."""
        # NOTA: la cancelación debe llegarle de verdad (task.cancel y await de la tarea); lo que
        # devuelva o lance después lo recoge el callback, nunca el log de asyncio.
        ejecucion.cancel()
        await self._esperar_cierre({ejecucion}, f"ejecutor de la tarea {task_id}")

    async def _esperar_cierre(self, pendientes: set[asyncio.Future], descripcion: str) -> None:
        """Espera con tope a que tareas ya canceladas terminen, sin volver a cancelarlas."""
        # NOTA: asyncio.wait no propaga la excepción de lo esperado ni lo cancela al agotarse:
        # si no cierra a tiempo queda registrado y el servicio sigue (el estado ya está escrito).
        terminadas, _ = await asyncio.wait(pendientes, timeout=self._espera_cancelacion_s)
        if not terminadas:
            logger.error(
                "se agotaron %s s esperando el cierre de %s",
                self._espera_cancelacion_s,
                descripcion,
            )

    def _recoger_resultado_ejecutor(self, ejecucion: asyncio.Future) -> None:
        """Recoge siempre el resultado de la tarea del ejecutor (punto 6): nada queda sin reclamar."""
        # NOTA: sin esto, la excepción de un ejecutor que ignoró la cancelación y murió después
        # dispararía el «Task exception was never retrieved» de asyncio con su texto completo.
        if ejecucion.cancelled():
            return
        try:
            ejecucion.result()
        except (Exception, asyncio.CancelledError) as error:
            # NOTA: solo el nombre de la clase en el warning: el texto puede traer secretos.
            logger.warning("el ejecutor terminó lanzando %s", type(error).__name__)

    def _guardar_resultado(
        self, task_id: str, ejecucion: asyncio.Future, escritorio: Escritorio
    ) -> None:
        """Puntos 5 y 6: guarda el resultado del ejecutor o el error interno con la clase."""
        # NOTA: la CancelledError se atrapa porque aquí el corredor no está cancelado: sería una
        # que el propio ejecutor decidió lanzar, y también es un fallo de la tarea (nunca en_curso).
        try:
            resultado = ejecucion.result()
        except (Exception, asyncio.CancelledError) as error:
            _registrar_excepcion(task_id, error)
            self._finalizar(
                task_id, FALLIDA, PREFIJO_ERROR_INTERNO + type(error).__name__, escritorio.password
            )
            return
        estado, resumen = _validar_resultado(resultado)
        self._finalizar(task_id, estado, resumen, escritorio.password)