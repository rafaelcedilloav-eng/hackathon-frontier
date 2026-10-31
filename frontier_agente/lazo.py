"""El lazo de una fase: capturar, decidir, vigilar y actuar sobre la pantalla."""
import json
import logging
import os
from typing import Protocol

from frontier_agente.guarda import es_aviso_gratuito, evaluar_accion, registrar_accion
from frontier_agente.tipos_agente import (
    ESCALA_MODELO,
    Accion,
    EstadoLazo,
    Intencion,
    ResultadoFase,
    Veredicto,
)

logger = logging.getLogger(__name__)

# NOTA: topes de una fase y textos fijos del historial y de las razones de fallar.
PASOS_POR_FASE = 14
MAX_BLOQUEOS = 3
MAX_ACCIONES_SIN_EFECTO = 3
MOTIVO_TEXTO_AJENO = "el texto no está en la tarea"
TIPOS_FINALES = ("leer", "terminar", "fallar")
DIRECCION_ABAJO = "abajo"
POSICION_PNG = 0  # NOTA: en la tupla (png, ejecuto) del paso anterior.
POSICION_EJECUTO = 1
NOTA_PANTALLA_CAMBIANDO = "la pantalla seguía cambiando"
PREFIJO_BLOQUEADA = "bloqueada: "
PLANTILLA_NOTA_BLOQUEO = "una instrucción en pantalla pedía escribir «{texto}»; no la ejecuté"
RAZON_BLOQUEOS = "demasiados intentos bloqueados"
RAZON_SIN_PASOS = "se agotaron los pasos"
RAZON_PANTALLA_INMOVIL = "la pantalla no cambia"
# NOTA: bloque 8: el clic gratuito que cierra un aviso o modal (FR-0153).
LINEA_AVISO_CERRADO = "cerré un aviso"
PLANTILLA_EVENTO_AVISO = "aviso cerrado: {titulo}"
TITULO_SIN_AVISO = "(sin título)"
CLAVE_EVENTO = "evento"

# NOTA: traza de depuración: la carpeta la fija AGENTE_TRAZA_DIR, que el agente
# pone por defecto en producción (logs/traza_<marca>); en pruebas puede faltar.
VARIABLE_TRAZA = "AGENTE_TRAZA_DIR"
NOMBRE_TRAZA_JSONL = "traza.jsonl"
PLANTILLA_NOMBRE_PNG = "{fase}_{paso:02d}.png"
CLAVE_LECTURA = "lectura"
CLAVE_TEXTO = "texto"
CLAVE_DIRECCION = "direccion"
CLAVE_VECES = "veces"


class Pantalla(Protocol):
    # NOTA: lo que el lazo exige a una pantalla (el ClienteRFB real y las falsas lo cumplen).
    ancho: int
    alto: int

    async def esperar_quieta(self) -> tuple[bool, bytes]: ...  # NOTA: captura quieta: dice si paró de cambiar y el PNG.
    async def clic(self, x: int, y: int) -> None: ...  # NOTA: clic en píxeles de la pantalla.
    async def escribir(self, texto: str) -> None: ...  # NOTA: escribe un texto en el control enfocado.
    async def tecla(self, nombre: str) -> None: ...  # NOTA: pulsa una tecla por su nombre.
    async def desplazar(self, x: int, y: int, abajo: bool, veces: int) -> None: ...  # NOTA: rueda del ratón sobre la lista en (x, y).


class Ojos(Protocol):
    # NOTA: lo que el lazo exige a los ojos (los de verdad y los falsos).
    async def decidir(self, png: bytes, objetivo: str, historial: list[str]) -> Accion: ...  # NOTA: de la captura y el objetivo a una sola acción.


def a_pixeles(x: int, y: int, ancho: int, alto: int) -> tuple[int, int]:
    # NOTA: pasa la escala 0-1000 del modelo a píxeles, recortado a los bordes de la pantalla.
    pixel_x = max(min(x * ancho // ESCALA_MODELO, ancho - 1), 0)
    pixel_y = max(min(y * alto // ESCALA_MODELO, alto - 1), 0)
    return pixel_x, pixel_y


class TrazaDeFase:
    """Registro de depuración de una fase: un PNG por paso y una línea JSON por acción."""

    def __init__(self, fase: str) -> None:
        # NOTA: activa si AGENTE_TRAZA_DIR existe (por defecto, siempre en
        # producción); aquí no llegan contraseña, token ni llave: la traza
        # solo guarda capturas y campos de la acción.
        self._fase = fase
        self._paso = 0
        self._carpeta = os.environ.get(VARIABLE_TRAZA) or ""
        self._activa = bool(self._carpeta) and self._preparar_carpeta()

    def _preparar_carpeta(self) -> bool:
        # NOTA: crea la carpeta de la traza; si no se puede, avisa y queda inactiva.
        try:
            os.makedirs(self._carpeta, exist_ok=True)
        except OSError as excepcion:
            logger.warning("la traza no pudo crear su carpeta (%s)", type(excepcion).__name__)
            return False
        return True

    def nuevo_paso(self, png: bytes) -> None:
        # NOTA: avanza el contador de la fase y guarda la captura que vieron los ojos.
        if not self._activa:
            return
        self._paso += 1
        nombre = PLANTILLA_NOMBRE_PNG.format(fase=self._fase, paso=self._paso)
        self._escribir_bytes(nombre, png)

    def registrar(self, accion: Accion, veredicto: Veredicto | None) -> None:
        # NOTA: una línea JSON por paso; veredicto None = acción terminal (leer/terminar/fallar);
        # el texto solo se registra si la acción se ejecutó de verdad en la pantalla.
        if not self._activa:
            return
        permitida = veredicto is None or veredicto.permitida
        linea = {
            "fase": self._fase,
            "paso": self._paso,
            "tipo": accion.tipo,
            "funcion": accion.funcion,
            "x": accion.x,
            "y": accion.y,
            "tecla": accion.tecla,
            "razon": accion.razon,
            "con_clic": accion.con_clic,
            "permitida": permitida,
            "motivo": "" if veredicto is None else veredicto.motivo,
        }
        if permitida and veredicto is not None:
            linea[CLAVE_TEXTO] = accion.texto
        if accion.tipo == "leer":
            linea[CLAVE_LECTURA] = accion.lectura
        if accion.tipo == "desplazar":
            linea[CLAVE_DIRECCION] = accion.direccion
            linea[CLAVE_VECES] = accion.veces
        self._agregar_linea(linea)

    def registrar_aviso(self, titulo: str) -> None:
        # NOTA: bloque 8: línea propia del aviso cerrado (clave evento); pasa por
        # _agregar_linea para que un fallo de disco nunca rompa la tarea.
        if not self._activa:
            return
        self._agregar_linea({
            "fase": self._fase,
            "paso": self._paso,
            CLAVE_EVENTO: PLANTILLA_EVENTO_AVISO.format(titulo=titulo),
        })

    def _escribir_bytes(self, nombre: str, contenido: bytes) -> None:
        # NOTA: un archivo por captura; si falla, avisa una vez y desactiva la traza.
        try:
            with open(os.path.join(self._carpeta, nombre), "wb") as archivo:
                archivo.write(contenido)
        except (OSError, TypeError, ValueError) as excepcion:
            logger.warning("la traza no pudo escribir %s (%s)", nombre, type(excepcion).__name__)
            self._activa = False

    def _agregar_linea(self, linea: dict) -> None:
        # NOTA: agrega la línea JSON del paso; si falla, avisa una vez y desactiva la traza.
        try:
            texto = json.dumps(linea, ensure_ascii=False)
        except (TypeError, ValueError) as excepcion:
            logger.warning("la traza no pudo serializar el paso (%s)", type(excepcion).__name__)
            return
        try:
            with open(os.path.join(self._carpeta, NOMBRE_TRAZA_JSONL), "a", encoding="utf-8") as archivo:
                archivo.write(texto + "\n")
        except (OSError, TypeError, ValueError) as excepcion:
            logger.warning("la traza no pudo registrar el paso (%s)", type(excepcion).__name__)
            self._activa = False


async def ejecutar_fase(fase: str, objetivo: str, intencion: Intencion,
                        pantalla: Pantalla, ojos: Ojos, estado: EstadoLazo, *,
                        max_pasos_fase: int = PASOS_POR_FASE) -> ResultadoFase:
    # NOTA: un paso = capturar, decidir, vigilar y (si el guarda lo permite) actuar;
    # los topes deciden cuándo la fase termina en fallar; las excepciones de pantalla salen.
    estado.fase = fase
    estado.campos_escritos.clear()
    historial: list[str] = []
    notas: list[str] = []
    traza = TrazaDeFase(fase)
    pasos_en_fase = 0
    anterior: tuple[bytes, bool] | None = None
    sin_efecto = 0
    while True:
        png, sin_efecto, falla = await _capturar(pantalla, historial, anterior, sin_efecto, notas)
        if falla is not None:
            return falla
        traza.nuevo_paso(png)
        accion = await ojos.decidir(png, objetivo, historial)
        resultado, anterior, gasto = await _manejar_accion(
            accion, png, intencion, estado, pantalla, traza, historial, notas,
            pasos_en_fase=pasos_en_fase, max_pasos_fase=max_pasos_fase,
        )
        if resultado is not None:
            return resultado
        pasos_en_fase += gasto


async def _manejar_accion(
    accion: Accion,
    png: bytes,
    intencion: Intencion,
    estado: EstadoLazo,
    pantalla: Pantalla,
    traza: TrazaDeFase,
    historial: list[str],
    notas: list[str],
    *,
    pasos_en_fase: int,
    max_pasos_fase: int,
) -> tuple[ResultadoFase | None, tuple[bytes, bool], int]:
    # NOTA: vigila y ejecuta la acción ya decidida; devuelve (el cierre de la fase
    # si lo hay, el `anterior` nuevo y los pasos de fase que gastó).
    if accion.tipo in TIPOS_FINALES:
        return _resultado_terminal(accion, traza, notas), (png, False), 0
    veredicto = evaluar_accion(accion, intencion, estado)
    gratuita = es_aviso_gratuito(accion, estado)  # NOTA: antes de registrar: la cuota cambia al cerrar.
    if not gratuita and pasos_en_fase >= max_pasos_fase:
        return ResultadoFase("fallar", razon=RAZON_SIN_PASOS, notas=tuple(notas)), (png, False), 0
    traza.registrar(accion, veredicto)
    if not veredicto.permitida:
        if _registrar_bloqueo(accion, veredicto, estado, historial, notas):
            return ResultadoFase("fallar", razon=RAZON_BLOQUEOS, notas=tuple(notas)), (png, False), 0
        return None, (png, False), 0
    await _actuar(accion, pantalla)
    registrar_accion(accion, intencion, estado)
    estado.bloqueos = 0  # NOTA: el tope cuenta bloqueos SEGUIDOS: una acción ejecutada reinicia (L2.1).
    if gratuita:
        traza.registrar_aviso(_titulo_de_aviso(accion))
        historial.append(LINEA_AVISO_CERRADO)
        return None, (png, False), 0  # NOTA: el aviso gratuito no gasta paso ni cuenta sin efecto.
    historial.append(_linea_de_lo_hecho(accion, pantalla))
    return None, (png, True), 1


def _resultado_terminal(accion: Accion, traza: TrazaDeFase, notas: list[str]) -> ResultadoFase:
    # NOTA: leer/terminar/fallar cierran la fase tal cual; solo fallar lleva razón (L2).
    traza.registrar(accion, None)
    razon = accion.razon if accion.tipo == "fallar" else ""
    return ResultadoFase(accion.tipo, lectura=accion.lectura, razon=razon, notas=tuple(notas))


def _titulo_de_aviso(accion: Accion) -> str:
    # NOTA: el título del aviso para la traza; sin texto va "(sin título)" (L3.5).
    return accion.texto or TITULO_SIN_AVISO


async def _capturar(pantalla: Pantalla, historial: list[str], anterior: tuple | None,
                    sin_efecto: int, notas: list[str]) -> tuple[bytes, int, ResultadoFase | None]:
    # NOTA: captura quieta (anotando si la pantalla seguía cambiando) y vigila el tope
    # de acciones seguidas sin efecto; devuelve el PNG, el contador renovado y la falla si aplica.
    quieta, png = await pantalla.esperar_quieta()
    if not quieta:
        historial.append(NOTA_PANTALLA_CAMBIANDO)
    sin_efecto = _sin_efecto_actual(png, anterior, sin_efecto)
    if sin_efecto >= MAX_ACCIONES_SIN_EFECTO:
        return png, sin_efecto, ResultadoFase("fallar", razon=RAZON_PANTALLA_INMOVIL, notas=tuple(notas))
    return png, sin_efecto, None


def _sin_efecto_actual(png: bytes, anterior: tuple[bytes, bool] | None, sin_efecto_previo: int) -> int:
    # NOTA: solo acumula cuando el paso anterior ejecutó algo y la pantalla no se movió;
    # `anterior` guarda la captura previa y si en ese paso se ejecutó una acción.
    if anterior is None or not anterior[POSICION_EJECUTO] or png != anterior[POSICION_PNG]:
        return 0
    return sin_efecto_previo + 1


async def _actuar(accion: Accion, pantalla: Pantalla) -> None:
    # NOTA: la única vía de entrada a la pantalla; el clic pasa por la escala a píxeles;
    # un escribir con con_clic enfoca primero con clic y luego escribe, en el mismo paso.
    if accion.tipo == "clic":
        await pantalla.clic(*a_pixeles(accion.x, accion.y, pantalla.ancho, pantalla.alto))
    elif accion.tipo == "escribir":
        if accion.con_clic:
            await pantalla.clic(*a_pixeles(accion.x, accion.y, pantalla.ancho, pantalla.alto))
        await pantalla.escribir(accion.texto)
    elif accion.tipo == "desplazar":
        pixel_x, pixel_y = a_pixeles(accion.x, accion.y, pantalla.ancho, pantalla.alto)
        await pantalla.desplazar(pixel_x, pixel_y, abajo=accion.direccion == DIRECCION_ABAJO, veces=accion.veces)
    else:
        await pantalla.tecla(accion.tecla)


def _registrar_bloqueo(
    accion: Accion,
    veredicto: Veredicto,
    estado: EstadoLazo,
    historial: list[str],
    notas: list[str],
) -> bool:
    # NOTA: nada llega a la pantalla; el historial y los bloqueos crecen, y las
    # órdenes de pantalla que se ignoraron quedan como nota para el resumen;
    # devuelve True si ya se alcanzó el tope de bloqueos seguidos.
    estado.bloqueos += 1
    historial.append(PREFIJO_BLOQUEADA + veredicto.motivo)
    if veredicto.motivo == MOTIVO_TEXTO_AJENO:
        notas.append(PLANTILLA_NOTA_BLOQUEO.format(texto=accion.texto))
    return estado.bloqueos >= MAX_BLOQUEOS


def _linea_de_lo_hecho(accion: Accion, pantalla: Pantalla) -> str:
    # NOTA: una línea corta para el historial que ven los ojos en el paso siguiente;
    # el escribir con con_clic menciona también el clic de foco.
    if accion.tipo == "clic":
        pixel_x, pixel_y = a_pixeles(accion.x, accion.y, pantalla.ancho, pantalla.alto)
        return f"clic en ({pixel_x}, {pixel_y})"
    if accion.tipo == "escribir":
        if accion.con_clic:
            pixel_x, pixel_y = a_pixeles(accion.x, accion.y, pantalla.ancho, pantalla.alto)
            return f"clic en ({pixel_x}, {pixel_y}) y escribí «{accion.texto}»"
        return f"escribí «{accion.texto}»"
    if accion.tipo == "desplazar":
        return f"desplacé la lista {accion.veces} veces hacia {accion.direccion}"
    return f"tecla {accion.tecla}"


# NOTA: las excepciones de pantalla (ErrorVNC, CancelledError…) salen del lazo tal cual:
# ejecutar_fase no las captura a propósito; quien decide qué hacer con ellas es el agente.
