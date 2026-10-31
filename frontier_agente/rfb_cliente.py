"""Cliente RFB 3.8 sobre WebSocket: ve la pantalla (PNG), hace clic, escribe y espera."""

import asyncio
import logging
import os
import struct
import time
import unicodedata
from types import TracebackType

from websockets.asyncio.client import connect

from frontier_agente import rfb_protocolo as proto
from frontier_agente.errores import (
    ErrorAutenticacion,
    ErrorConfiguracion,
    ErrorConexion,
    ErrorProtocolo,
    ErrorTiempo,
)

logger = logging.getLogger(__name__)

# NOTA: constantes de comportamiento que fija la tabla C.
CLIC_MS = 150
MILISEGUNDOS_POR_SEGUNDO = 1000
PAUSA_TECLA_S = 0.02
PAUSA_RUEDA_S = 0.06
INTERVALO_QUIETA_S = 0.25
TOPE_QUIETA_S = 3.0
ESPERA_REPINTADO_S = 1.0
TOPE_OPERACION_S = 10.0
TOPE_CIERRE_S = 3.0

# NOTA: constantes del protocolo RFB que este cliente habla.
VERSION_RFB = b"RFB 003.008\n"
SALTO_DE_LINEA = b"\n"
PREFIJO_VERSION = b"RFB "
CORTE_VERSION_MAYOR = slice(4, 7)
POSICION_PUNTO_VERSION = 7
CORTE_VERSION_MENOR = slice(8, 11)
LARGO_VERSION_SIN_SALTO = 11
VERSION_MAYOR_MINIMA = 3
VERSION_MENOR_MINIMA = 8
SUBPROTOCOLO = "binary"
SEGURIDAD_VNC_AUTH = 2
RESULTADO_SEGURIDAD_OK = 0
CLIENT_INIT_COMPARTIDO = 1
LARGO_U16 = 2
LARGO_U32 = 4
LARGO_DIMENSIONES_PANTALLA = 2 * LARGO_U16
LARGO_FORMATO_PIXEL = 16
LARGO_CABECERA_RECTANGULO = 8
LARGO_CABECERA_TABLA_COLORES = 5
LARGO_RELLENO_CUT_TEXT = 3
BYTES_POR_COLOR = 6

# NOTA: tipos de mensaje que el servidor puede mandar durante una captura.
TIPO_UPDATE = 0
TIPO_TABLA_COLORES = 1
TIPO_CAMPANA = 2
TIPO_CUT_TEXT = 3

KEYSYM_CONTROL_IZQUIERDO = 0xFFE3
KEYSYM_LETRA_A = 0x61
MASCARA_SIN_BOTONES = 0
MASCARA_BOTON_IZQUIERDO = 1
MASCARA_RUEDA_ABAJO = 1 << 4  # botón 5 de X11: rueda hacia abajo
MASCARA_RUEDA_ARRIBA = 1 << 3  # botón 4 de X11: rueda hacia arriba
VECES_RUEDA_POR_OMISION = 3
VECES_RUEDA_MINIMAS = 1
VECES_RUEDA_MAXIMAS = 10

# NOTA: variables de entorno que alimenta desde_entorno().
VARIABLE_URL = "FRONTIER_ESCRITORIO_URL"
VARIABLE_PASSWORD = "FRONTIER_ESCRITORIO_PASS"


def _desempaquetar(formato: str, crudo: bytes) -> tuple:
    # NOTA: struct.error a mitad de una lectura es protocolo roto, no crash (C37).
    try:
        return struct.unpack(formato, crudo)
    except struct.error:
        raise ErrorProtocolo(
            f"mensaje del servidor con tamaño inesperado ({formato})") from None


class ClienteRFB:
    """Cliente VNC/RFB 3.8 por WebSocket; la única vía del agente hacia la app."""

    def __init__(self, url: str, password: str, *, tope_lectura_s: float = 10.0) -> None:
        # NOTA: guarda la configuración; nada de red aquí (conectar() la abre).
        self._url = url
        self._password = password
        self._tope = tope_lectura_s
        self._websocket = None
        self._ancho = 0
        self._alto = 0
        self._buffer = bytearray()
        self._framebuffer = bytearray()
        self._t_ultimo_evento = None

    @property
    def ancho(self) -> int:
        # NOTA: ancho de pantalla que reportó el ServerInit.
        return self._ancho

    @property
    def alto(self) -> int:
        # NOTA: alto de pantalla que reportó el ServerInit.
        return self._alto

    @classmethod
    def desde_entorno(cls) -> "ClienteRFB":
        # NOTA: lee URL y contraseña del entorno; nombra la variable que falte.
        url = os.environ.get(VARIABLE_URL)
        password = os.environ.get(VARIABLE_PASSWORD)
        if not url:
            raise ErrorConfiguracion(f"falta la variable de entorno {VARIABLE_URL}")
        if not password:
            raise ErrorConfiguracion(f"falta la variable de entorno {VARIABLE_PASSWORD}")
        return cls(url, password)

    async def __aenter__(self) -> "ClienteRFB":
        # NOTA: conecta al entrar al bloque async with.
        await self.conectar()
        return self

    async def __aexit__(self, tipo_excepcion: type[BaseException] | None,
                        valor_excepcion: BaseException | None,
                        traza_excepcion: TracebackType | None) -> None:
        # NOTA: cierra SIEMPRE, también cuando el bloque lanzó; no suprime la excepción.
        await self.cerrar()

    # ------------------------------------------------------------ conexión
    async def conectar(self) -> None:
        # NOTA: abre el WebSocket y corre el handshake RFB 3.8 completo.
        if self._websocket is not None:
            return
        self._buffer = bytearray()
        try:
            self._websocket = await asyncio.wait_for(
                connect(self._url, subprotocols=[SUBPROTOCOLO], max_size=None),
                TOPE_OPERACION_S)
        except TimeoutError:
            raise ErrorTiempo(
                f"la conexión agotó el tope de {TOPE_OPERACION_S} s") from None
        except Exception as exc:
            # NOTA: la causa podría traer la URL; con from None no se encadena.
            raise ErrorConexion(
                f"no se pudo abrir el WebSocket ({type(exc).__name__})") from None
        try:
            await self._intercambiar_version()
            await self._elegir_seguridad()
            await self._autenticar()
            await self._leer_server_init()
            await self._enviar(proto.msg_set_pixel_format())
            await self._enviar(proto.msg_set_encodings())
        except BaseException:
            # NOTA: incluso una cancelación a mitad del handshake deja el WebSocket cerrado.
            await self.cerrar()
            raise

    async def cerrar(self) -> None:
        # NOTA: cierra el WebSocket con su propio tope; idempotente; fallo => warning sin secretos.
        if self._websocket is None:
            return
        websocket = self._websocket
        self._websocket = None
        self._buffer.clear()
        try:
            await asyncio.wait_for(websocket.close(), TOPE_CIERRE_S)
        except Exception as exc:
            logger.warning("el cierre del WebSocket falló (%s)", type(exc).__name__)

    # ------------------------------------------------------------ handshake
    async def _intercambiar_version(self) -> None:
        # NOTA: valida la versión del servidor; menor que 3.8 no se acepta.
        recibida = await self._leer_exacto(len(VERSION_RFB))
        try:
            mayor = int(recibida[CORTE_VERSION_MAYOR])
            menor = int(recibida[CORTE_VERSION_MENOR])
            valida = (recibida.startswith(PREFIJO_VERSION)
                      and chr(recibida[POSICION_PUNTO_VERSION]) == "."
                      and recibida.endswith(SALTO_DE_LINEA))
        except ValueError:
            valida = False
        if not valida or mayor != VERSION_MAYOR_MINIMA or menor < VERSION_MENOR_MINIMA:
            texto = recibida[:LARGO_VERSION_SIN_SALTO].decode("ascii", "replace")
            raise ErrorProtocolo(f"versión RFB no soportada: {texto}")
        await self._enviar(VERSION_RFB)

    async def _elegir_seguridad(self) -> None:
        # NOTA: exige el tipo 2 (VNC auth); con 0 tipos lee la razón del servidor.
        cantidad = (await self._leer_exacto(proto.LARGO_U8))[0]
        if cantidad == 0:
            razon = await self._leer_texto_con_largo()
            raise ErrorProtocolo(f"el servidor rechazó la conexión: {razon}")
        tipos = await self._leer_exacto(cantidad)
        if SEGURIDAD_VNC_AUTH not in tipos:
            raise ErrorProtocolo("el servidor no ofrece el tipo de seguridad 2 (VNC auth)")
        await self._enviar(bytes([SEGURIDAD_VNC_AUTH]))

    async def _autenticar(self) -> None:
        # NOTA: responde el desafío DES y comprueba el SecurityResult del servidor.
        desafio = await self._leer_exacto(proto.LARGO_DESAFIO)
        await self._enviar(proto.respuesta_desafio(self._password, desafio))
        resultado = _desempaquetar("!I", await self._leer_exacto(LARGO_U32))[0]
        if resultado != RESULTADO_SEGURIDAD_OK:
            razon = await self._leer_texto_con_largo()
            raise ErrorAutenticacion(f"el servidor rechazó la autenticación: {razon}")

    async def _leer_server_init(self) -> None:
        # NOTA: manda ClientInit (shared=1) y lee ancho, alto, formato de píxel y nombre.
        await self._enviar(bytes([CLIENT_INIT_COMPARTIDO]))
        self._ancho, self._alto = _desempaquetar(
            "!HH", await self._leer_exacto(LARGO_DIMENSIONES_PANTALLA))
        await self._leer_exacto(LARGO_FORMATO_PIXEL)
        nombre = await self._leer_texto_con_largo()
        self._framebuffer = bytearray(self._ancho * self._alto * proto.BYTES_POR_PIXEL)
        logger.debug("escritorio conectado: %dx%d, nombre de %d caracteres",
                     self._ancho, self._alto, len(nombre))

    # ------------------------------------------------------------ lectura/escritura crudas
    async def _leer_texto_con_largo(self) -> str:
        # NOTA: texto RFB: largo u32 big-endian y luego esos bytes.
        largo = _desempaquetar("!I", await self._leer_exacto(LARGO_U32))[0]
        crudo = await self._leer_exacto(largo)
        return crudo.decode("utf-8", "replace")

    async def _leer_exacto(self, cantidad: int) -> bytes:
        # NOTA: saca `cantidad` bytes del búfer; lo rellena del WebSocket con tope por mensaje.
        self._exigir_conexion()
        while len(self._buffer) < cantidad:
            try:
                trozo = await asyncio.wait_for(self._websocket.recv(), self._tope)
            except TimeoutError:
                raise ErrorTiempo(f"sin respuesta del servidor en {self._tope} s") from None
            except Exception as exc:
                raise ErrorConexion(
                    f"lectura del WebSocket falló ({type(exc).__name__})") from None
            if isinstance(trozo, str):
                # NOTA: RFB viaja en binario; un mensaje de texto rompe el flujo (C34).
                raise ErrorProtocolo("el servidor mandó un mensaje WebSocket de texto")
            self._buffer.extend(trozo)
        resultado = bytes(self._buffer[:cantidad])
        del self._buffer[:cantidad]
        return resultado

    async def _enviar(self, mensaje_rfb: bytes) -> None:
        # NOTA: prosa 10 / C31: un mensaje RFB completo en UN solo mensaje WebSocket binario.
        self._exigir_conexion()
        try:
            await asyncio.wait_for(self._websocket.send(mensaje_rfb), TOPE_OPERACION_S)
        except TimeoutError:
            # NOTA: un envío agotado deja el flujo inutilizable: se corta la conexión.
            await self.cerrar()
            raise ErrorTiempo(
                f"el envío agotó el tope de {TOPE_OPERACION_S} s") from None
        except Exception as exc:
            raise ErrorConexion(
                f"envío al WebSocket falló ({type(exc).__name__})") from None

    def _exigir_conexion(self) -> None:
        # NOTA: todos los métodos de red comprueban primero que la sesión viva.
        if self._websocket is None:
            raise ErrorConexion("la conexión no está abierta")

    # ------------------------------------------------------------ capturas
    async def captura_bgrx(self) -> bytes:
        # NOTA: pide la pantalla completa (no incremental) y llena el framebuffer local.
        self._exigir_conexion()
        await self._enviar(proto.msg_update_request(False, 0, 0, self._ancho, self._alto))
        try:
            await self._procesar_hasta_update()
        except (ErrorTiempo, ErrorProtocolo):
            # NOTA: a mitad de una lectura el flujo ya no es confiable: se corta la conexión.
            await self.cerrar()
            raise
        return bytes(self._framebuffer)

    async def captura(self) -> bytes:
        # NOTA: la misma captura de arriba, pero como PNG; no manda entrada.
        bgrx = await self.captura_bgrx()
        return proto.png_desde_bgrx(bgrx, self._ancho, self._alto)

    async def _procesar_hasta_update(self) -> None:
        # NOTA: come mensajes del servidor hasta el update; los ajenos se descartan.
        while True:
            tipo = (await self._leer_exacto(proto.LARGO_U8))[0]
            if tipo == TIPO_UPDATE:
                await self._copiar_rectangulos()
                return
            if tipo == TIPO_CAMPANA:
                continue
            if tipo == TIPO_TABLA_COLORES:
                await self._descartar_tabla_colores()
            elif tipo == TIPO_CUT_TEXT:
                await self._descartar_cut_text()
            else:
                raise ErrorProtocolo(f"tipo de mensaje del servidor no soportado: {tipo}")

    async def _copiar_rectangulos(self) -> None:
        # NOTA: lee un FramebufferUpdate y copia cada rectángulo Raw (el único códec).
        await self._leer_exacto(proto.LARGO_U8)  # byte de relleno tras el tipo
        cantidad = _desempaquetar("!H", await self._leer_exacto(LARGO_U16))[0]
        for _ in range(cantidad):
            x, y, ancho, alto = _desempaquetar(
                "!HHHH", await self._leer_exacto(LARGO_CABECERA_RECTANGULO))
            codificacion = _desempaquetar("!i", await self._leer_exacto(LARGO_U32))[0]
            if codificacion != proto.CODIFICACION_RAW:
                raise ErrorProtocolo(f"codificación no soportada: {codificacion}")
            self._validar_rectangulo(x, y, ancho, alto)
            pixeles = await self._leer_exacto(ancho * alto * proto.BYTES_POR_PIXEL)
            self._pegar_rectangulo(x, y, ancho, alto, pixeles)

    def _validar_rectangulo(self, x: int, y: int, ancho: int, alto: int) -> None:
        # NOTA: un rectángulo fuera de pantalla rompería el framebuffer local.
        if x < 0 or y < 0 or x + ancho > self._ancho or y + alto > self._alto:
            raise ErrorProtocolo(f"rectángulo fuera de la pantalla: {ancho}x{alto} en ({x},{y})")

    def _pegar_rectangulo(self, x: int, y: int, ancho: int, alto: int,
                          pixeles: bytes) -> None:
        # NOTA: copia fila por fila el rectángulo Raw a su posición del framebuffer.
        fila_bytes = ancho * proto.BYTES_POR_PIXEL
        for fila in range(alto):
            destino = ((y + fila) * self._ancho + x) * proto.BYTES_POR_PIXEL
            origen = fila * fila_bytes
            self._framebuffer[destino:destino + fila_bytes] = pixeles[origen:origen + fila_bytes]

    async def _descartar_tabla_colores(self) -> None:
        # NOTA: SetColourMapEntries: relleno u8, primer color u16, cantidad u16 y 6 bytes/color.
        _, cantidad_colores = _desempaquetar(
            "!xHH", await self._leer_exacto(LARGO_CABECERA_TABLA_COLORES))
        await self._leer_exacto(cantidad_colores * BYTES_POR_COLOR)

    async def _descartar_cut_text(self) -> None:
        # NOTA: ServerCutText: 3 de relleno, largo u32 y el texto; se tira sin desincronizar.
        await self._leer_exacto(LARGO_RELLENO_CUT_TEXT)
        texto = await self._leer_texto_con_largo()
        logger.debug("ServerCutText descartado (%d caracteres)", len(texto))

    # ------------------------------------------------------------ entrada
    async def _pulsar_keysym(self, keysym: int) -> None:
        # NOTA: patrón abajo-pausa-arriba que comparten escribir y tecla.
        await self._enviar(proto.msg_key(True, keysym))
        await asyncio.sleep(PAUSA_TECLA_S)
        await self._enviar(proto.msg_key(False, keysym))

    async def clic(self, x: int, y: int) -> None:
        # NOTA: valida el rango ANTES de mandar; mueve, pulsa, espera CLIC_MS y suelta.
        if not 0 <= x < self._ancho or not 0 <= y < self._alto:
            raise ValueError(f"clic fuera de la pantalla {self._ancho}x{self._alto}: ({x}, {y})")
        self._exigir_conexion()
        await self._enviar(proto.msg_pointer(MASCARA_SIN_BOTONES, x, y))
        await self._enviar(proto.msg_pointer(MASCARA_BOTON_IZQUIERDO, x, y))
        await asyncio.sleep(CLIC_MS / MILISEGUNDOS_POR_SEGUNDO)
        await self._enviar(proto.msg_pointer(MASCARA_SIN_BOTONES, x, y))
        self._t_ultimo_evento = time.monotonic()

    async def desplazar(self, x: int, y: int, abajo: bool, veces: int = VECES_RUEDA_POR_OMISION) -> None:
        # NOTA: valida TODO antes de mandar; por cada vez, rueda abajo-pausa-suelta en (x, y).
        if not 0 <= x < self._ancho or not 0 <= y < self._alto:
            raise ValueError(
                f"desplazar fuera de la pantalla {self._ancho}x{self._alto}: ({x}, {y})")
        if not VECES_RUEDA_MINIMAS <= veces <= VECES_RUEDA_MAXIMAS:
            raise ValueError(
                f"las veces de desplazar deben estar entre "
                f"{VECES_RUEDA_MINIMAS} y {VECES_RUEDA_MAXIMAS}: {veces}")
        self._exigir_conexion()
        mascara = MASCARA_RUEDA_ABAJO if abajo else MASCARA_RUEDA_ARRIBA
        for _ in range(veces):
            await self._enviar(proto.msg_pointer(mascara, x, y))
            await asyncio.sleep(PAUSA_RUEDA_S)
            await self._enviar(proto.msg_pointer(MASCARA_SIN_BOTONES, x, y))
        self._t_ultimo_evento = time.monotonic()

    async def escribir(self, texto: str) -> None:
        # NOTA: NFC y valida TODO antes de mandar; luego Ctrl+A y cada carácter con _pulsar_keysym.
        normalizado = unicodedata.normalize("NFC", texto)
        if not normalizado:
            raise ValueError("el texto está vacío")
        keysyms = [proto.keysym_de_caracter(caracter) for caracter in normalizado]
        self._exigir_conexion()
        await self._enviar(proto.msg_key(True, KEYSYM_CONTROL_IZQUIERDO))
        await self._pulsar_keysym(KEYSYM_LETRA_A)
        await self._enviar(proto.msg_key(False, KEYSYM_CONTROL_IZQUIERDO))
        await asyncio.sleep(PAUSA_TECLA_S)
        for keysym in keysyms:
            await self._pulsar_keysym(keysym)
            await asyncio.sleep(PAUSA_TECLA_S)
        self._t_ultimo_evento = time.monotonic()

    async def tecla(self, nombre: str) -> None:
        # NOTA: valida el nombre antes de mandar nada; abajo-pausa-arriba.
        keysym = proto.keysym_de_tecla(nombre)
        self._exigir_conexion()
        await self._pulsar_keysym(keysym)
        self._t_ultimo_evento = time.monotonic()

    async def esperar_quieta(self) -> tuple[bool, bytes]:
        # NOTA: quieta con dos capturas iguales seguidas; el tope corre desde la llamada (C32).
        self._exigir_conexion()
        fin = time.monotonic() + TOPE_QUIETA_S
        await self._esperar_repintado()
        actual = await self.captura_bgrx()
        while time.monotonic() < fin:
            await asyncio.sleep(INTERVALO_QUIETA_S)
            anterior = actual
            actual = await self.captura_bgrx()
            if actual == anterior:
                return True, proto.png_desde_bgrx(actual, self._ancho, self._alto)
        return False, proto.png_desde_bgrx(actual, self._ancho, self._alto)

    async def _esperar_repintado(self) -> None:
        # NOTA: tras una acción reciente la pantalla vieja tarda en irse; no se captura antes.
        if self._t_ultimo_evento is None:
            return
        restante = ESPERA_REPINTADO_S - (time.monotonic() - self._t_ultimo_evento)
        if restante > 0:
            await asyncio.sleep(restante)
