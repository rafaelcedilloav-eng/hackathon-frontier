"""
Servidor RFB 3.8 falso para pruebas del ClienteRFB.

Capacidades (según el encargo 001):
- Aceptar o rechazar la contraseña (VNC auth con DES), o aceptar cualquiera.
- Ofrecer otros tipos de seguridad, o ninguno con una razón.
- Mandar todo el flujo en fragmentos de 1 byte por mensaje WebSocket.
- Servir pantallas en una secuencia, o generar una pantalla distinta por petición.
- Retrasar la respuesta de actualización, o cambiar de pantalla un tiempo
  después de recibir un pointer-up.
- Responder con un mensaje de tipo desconocido o con codificación inválida.
- Insertar Bell y ServerCutText antes del update, y partir la pantalla en 2 rectángulos.
- Insertar un SetColourMapEntries justo antes del FramebufferUpdate (C37).
- Aceptar la conexión sin saludar (C33) y mandar un mensaje WebSocket de texto a
  mitad de una captura (C34).
- Registrar con marca de tiempo cada mensaje que recibe, y los límites de cada
  mensaje WebSocket que recibe (para C31).
- Avisar cuándo se cerró el WebSocket.
"""
import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import List, Optional

from websockets.asyncio.server import serve, ServerConnection

logger = logging.getLogger(__name__)

# Constantes RFB
RFB_VERSION = b"RFB 003.008\n"
SECURITY_TYPE_VNC_AUTH = 2
SECURITY_RESULT_OK = 0
SECURITY_RESULT_FAILED = 1

# Tipos de mensaje del servidor
SERVER_FRAMEBUFFER_UPDATE = 0
SERVER_SET_COLOUR_MAP_ENTRIES = 1
SERVER_BELL = 2
SERVER_CUT_TEXT = 3

# Tipos de mensaje del cliente
CLIENT_SET_PIXEL_FORMAT = 0
CLIENT_SET_ENCODINGS = 2
CLIENT_FRAMEBUFFER_UPDATE_REQUEST = 3
CLIENT_KEY_EVENT = 4
CLIENT_POINTER_EVENT = 5
CLIENT_CUT_TEXT = 6

# Codificaciones
ENCODING_RAW = 0
ENCODING_TIGHT = 7

# Modos de respuesta a un FramebufferUpdateRequest
MODO_RAW = "raw"
MODO_NO_RESPONDER = "no_responder"
MODO_TIPO_99 = "tipo_99"
MODO_ENCODING_7 = "encoding_7"

TIPO_MENSAJE_DESCONOCIDO = 99


@dataclass
class RegistroMensaje:
    """Registro de un mensaje recibido con marca de tiempo (time.monotonic)."""
    tipo: str
    datos: bytes
    timestamp: float


@dataclass
class Pantalla:
    """Una pantalla para servir (datos BGRX: ancho * alto * 4 bytes)."""
    ancho: int
    alto: int
    datos_bgrx: bytes


@dataclass
class ConfiguracionServidor:
    """Configuración del servidor falso."""
    password: str = "password"
    acepta_cualquiera: bool = False
    tipos_seguridad: List[int] = field(default_factory=lambda: [SECURITY_TYPE_VNC_AUTH])
    razon_sin_tipos: str = "too many"
    version_rfb: bytes = RFB_VERSION
    desafio: bytes = field(default_factory=lambda: bytes(range(16)))
    pantallas: List[Pantalla] = field(default_factory=list)
    # Retrasa la respuesta a cada petición de actualización (segundos).
    retraso_cambio_pantalla: float = 0.0
    # Manda todo (handshake y updates) de 1 byte por mensaje WebSocket.
    fragmentar_1_byte: bool = False
    # raw | no_responder | tipo_99 | encoding_7
    modo_respuesta: str = MODO_RAW
    # Envía un Bell y un ServerCutText("hola") antes del update.
    insertar_bell_y_cuttext: bool = False
    # Parte la pantalla en 2 rectángulos (mitades superior e inferior).
    dos_rectangulos: bool = False
    # Genera una pantalla distinta por petición (byte 0 = contador).
    generar_distintas: bool = False
    # Sirve pantallas[0] hasta este tiempo tras un pointer-up, luego pantallas[1].
    cambiar_tras_pointer_up_s: float = 0.0
    # Número máximo de actualizaciones a servir; después ignora las peticiones.
    actualizaciones_maximas: Optional[int] = None
    # Acepta el WebSocket pero nunca contesta el saludo (C33).
    nunca_saludar: bool = False
    # Manda este texto como mensaje WebSocket de TEXTO entre los dos
    # rectángulos de cada update (C34).
    texto_inesperado: Optional[str] = None
    # Manda un SetColourMapEntries (tipo 1) justo antes del update (C37).
    insertar_set_colour_map: bool = False


class ServidorRFBFalso:
    """Servidor RFB 3.8 falso sobre WebSocket (websockets.asyncio)."""

    def __init__(self, config: ConfiguracionServidor):
        self.config = config
        self.registros: List[RegistroMensaje] = []
        self.subprotocol_solicitado: str = ""
        self._websocket: Optional[ServerConnection] = None
        self._servidor = None
        self._puerto: int = 0
        self._cerrado = asyncio.Event()
        self._handshake_completado = asyncio.Event()
        self._indice_pantalla = 0
        self._contador_distintas = 0
        self._updates_servidos = 0
        self._t_pointer_up: Optional[float] = None
        self._buzon = bytearray()
        # Cada mensaje WebSocket recibido, tal cual llegó (límites incluidos).
        self.mensajes_ws: List[bytes] = []

    # ------------------------------------------------------------------ API
    @property
    def puerto(self) -> int:
        return self._puerto

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self._puerto}"

    def registrar(self, tipo: str, datos: bytes) -> None:
        """Registra un mensaje recibido con marca de tiempo."""
        self.registros.append(RegistroMensaje(tipo, datos, time.monotonic()))
        logger.debug("Recibido %s: %s", tipo, datos.hex())

    def registros_de(self, tipo: str) -> List[RegistroMensaje]:
        """Todos los registros de un tipo, en orden de llegada."""
        return [r for r in self.registros if r.tipo == tipo]

    def limpiar_registros(self) -> None:
        self.registros.clear()

    async def esperar_cierre(self, timeout: float = 5.0) -> bool:
        """Espera a que el WebSocket se cierre. True si cerró dentro del tiempo."""
        try:
            await asyncio.wait_for(self._cerrado.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def esperar_handshake(self, timeout: float = 5.0) -> bool:
        """Espera a que se complete el handshake. True si completó a tiempo."""
        try:
            await asyncio.wait_for(self._handshake_completado.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def iniciar(self) -> None:
        """Inicia el servidor en 127.0.0.1 y puerto 0 (asignado por el SO)."""
        self._cerrado.clear()
        self._servidor = await serve(self._handler, "127.0.0.1", 0)
        sockets = self._servidor.sockets
        if sockets:
            self._puerto = sockets[0].getsockname()[1]
        logger.info("Servidor RFB falso iniciado en puerto %s", self._puerto)

    async def cerrar(self) -> None:
        """Cierra el servidor."""
        if self._servidor:
            self._servidor.close()
            await self._servidor.wait_closed()
        self._cerrado.set()

    # ------------------------------------------------------------ internals
    async def _enviar(self, datos: bytes) -> None:
        """Envía datos; con fragmentar_1_byte manda 1 byte por mensaje."""
        if self._websocket is None:
            return
        if self.config.fragmentar_1_byte:
            for b in datos:
                await self._websocket.send(bytes([b]))
        else:
            await self._websocket.send(datos)

    async def _leer_exacto(self, n: int) -> bytes:
        """Lee exactamente n bytes del búfer interno. RFB es un flujo: el exceso
        de bytes de cada mensaje WebSocket se conserva para la siguiente lectura."""
        while len(self._buzon) < n:
            chunk = await self._websocket.recv()
            if isinstance(chunk, str):
                chunk = chunk.encode("latin-1")
            self.mensajes_ws.append(bytes(chunk))
            self._buzon.extend(chunk)
        datos = bytes(self._buzon[:n])
        del self._buzon[:n]
        return datos

    def _clave_vnc(self, password: str) -> bytes:
        """Clave VNC: latin-1, 8 bytes, rellenada/truncada, con el orden de los
        bits de cada byte invertido (0x61 -> 0x86), como pide el protocolo."""
        pwd_bytes = password.encode("latin-1")
        if len(pwd_bytes) > 8:
            pwd_bytes = pwd_bytes[:8]
        elif len(pwd_bytes) < 8:
            pwd_bytes = pwd_bytes + b"\x00" * (8 - len(pwd_bytes))
        return bytes(int(format(b, "08b")[::-1], 2) for b in pwd_bytes)

    def _pantalla_actual(self) -> Pantalla:
        """La pantalla que toca servir ahora, según la configuración."""
        cfg = self.config
        base = cfg.pantallas[0] if cfg.pantallas else Pantalla(64, 48, bytes(64 * 48 * 4))
        if cfg.cambiar_tras_pointer_up_s > 0 and self._t_pointer_up is not None:
            if time.monotonic() - self._t_pointer_up >= cfg.cambiar_tras_pointer_up_s:
                return cfg.pantallas[1]
            return cfg.pantallas[0]
        if cfg.generar_distintas:
            datos = bytearray(base.ancho * base.alto * 4)
            datos[0] = self._contador_distintas & 0xFF
            return Pantalla(base.ancho, base.alto, bytes(datos))
        if self._indice_pantalla < len(cfg.pantallas):
            return cfg.pantallas[self._indice_pantalla]
        return base

    async def _manejar_handshake(self) -> bool:
        """Handshake RFB 3.8. True si fue bien, False si hay que cerrar."""
        await self._enviar(self.config.version_rfb)

        version_cliente = await self._leer_exacto(len(RFB_VERSION))
        self.registrar("ClientVersion", version_cliente)
        if version_cliente != RFB_VERSION:
            return False

        if not self.config.tipos_seguridad:
            razon = self.config.razon_sin_tipos.encode("utf-8")
            await self._enviar(struct.pack("!B", 0))
            await self._enviar(struct.pack("!I", len(razon)))
            await self._enviar(razon)
            return False

        await self._enviar(struct.pack("!B", len(self.config.tipos_seguridad)))
        for t in self.config.tipos_seguridad:
            await self._enviar(struct.pack("!B", t))

        tipo_elegido = (await self._leer_exacto(1))[0]
        self.registrar("SecurityType", bytes([tipo_elegido]))
        if tipo_elegido != SECURITY_TYPE_VNC_AUTH:
            return False

        await self._enviar(self.config.desafio)
        respuesta = await self._leer_exacto(16)
        self.registrar("ChallengeResponse", respuesta)

        if not self.config.acepta_cualquiera:
            from Crypto.Cipher import DES
            clave = self._clave_vnc(self.config.password)
            cipher = DES.new(clave, DES.MODE_ECB)
            esperada = cipher.encrypt(self.config.desafio[:8]) + cipher.encrypt(self.config.desafio[8:])
            if respuesta != esperada:
                await self._enviar(struct.pack("!I", SECURITY_RESULT_FAILED))
                razon = b"Authentication failed"
                await self._enviar(struct.pack("!I", len(razon)))
                await self._enviar(razon)
                return False

        await self._enviar(struct.pack("!I", SECURITY_RESULT_OK))

        client_init = await self._leer_exacto(1)
        self.registrar("ClientInit", client_init)

        pantalla = self._pantalla_actual()
        await self._enviar(struct.pack("!HH", pantalla.ancho, pantalla.alto))
        # Formato de píxel: 32 bpp, profundidad 24, little-endian, color verdadero,
        # máximos 255/255/255, desplazamientos 16/8/0 (bytes B,G,R,X) = 16 bytes.
        pixel_format = struct.pack("!BBBBHHHBBB3x", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        await self._enviar(pixel_format)
        nombre = b"Servidor Falso"
        await self._enviar(struct.pack("!I", len(nombre)))
        await self._enviar(nombre)

        self._handshake_completado.set()
        return True

    async def _enviar_rectangulo(self, x: int, y: int, ancho: int, alto: int,
                                 datos: bytes, encoding: int) -> None:
        await self._enviar(struct.pack("!HHHHI", x, y, ancho, alto, encoding))
        await self._enviar(datos)

    async def _enviar_framebuffer_update(self) -> None:
        """Responde a un FramebufferUpdateRequest según el modo configurado."""
        cfg = self.config
        if cfg.modo_respuesta == MODO_NO_RESPONDER:
            return
        if cfg.actualizaciones_maximas is not None and self._updates_servidos >= cfg.actualizaciones_maximas:
            return
        if cfg.retraso_cambio_pantalla > 0:
            await asyncio.sleep(cfg.retraso_cambio_pantalla)
        if cfg.modo_respuesta == MODO_TIPO_99:
            await self._enviar(bytes([TIPO_MENSAJE_DESCONOCIDO]) + b"\x00\x00\x00")
            return

        if cfg.insertar_bell_y_cuttext:
            await self._enviar(bytes([SERVER_BELL]))
            texto = b"hola"
            await self._enviar(bytes([SERVER_CUT_TEXT]) + b"\x00\x00\x00"
                               + struct.pack("!I", len(texto)) + texto)
        if cfg.insertar_set_colour_map:
            # C37: tipo 1 + 1 relleno + primer color u16 + cantidad u16 = 2
            # + 2 colores de 6 bytes (R, G y B en u16 cada uno).
            colores = struct.pack("!HHHHHH", 0x0001, 0x0002, 0x0003,
                                  0x0004, 0x0005, 0x0006)
            await self._enviar(bytes([SERVER_SET_COLOUR_MAP_ENTRIES]) + b"\x00"
                               + struct.pack("!HH", 0, 2) + colores)

        pantalla = self._pantalla_actual()
        encoding = ENCODING_TIGHT if cfg.modo_respuesta == MODO_ENCODING_7 else ENCODING_RAW
        texto_en_medio = cfg.texto_inesperado is not None
        num_rects = 2 if (cfg.dos_rectangulos or texto_en_medio) else 1
        await self._enviar(struct.pack("!BBH", SERVER_FRAMEBUFFER_UPDATE, 0, num_rects))
        if num_rects == 1:
            await self._enviar_rectangulo(0, 0, pantalla.ancho, pantalla.alto,
                                          pantalla.datos_bgrx, encoding)
        else:
            mitad = pantalla.alto // 2
            fila_bytes = pantalla.ancho * 4
            await self._enviar_rectangulo(0, 0, pantalla.ancho, mitad,
                                          pantalla.datos_bgrx[:mitad * fila_bytes], encoding)
            if texto_en_medio:
                # C34: mensaje WebSocket de TEXTO a mitad de la captura.
                await self._websocket.send(cfg.texto_inesperado)
            await self._enviar_rectangulo(0, mitad, pantalla.ancho, pantalla.alto - mitad,
                                          pantalla.datos_bgrx[mitad * fila_bytes:], encoding)

        self._updates_servidos += 1
        if cfg.generar_distintas:
            self._contador_distintas += 1
        elif self._indice_pantalla < len(cfg.pantallas) - 1:
            self._indice_pantalla += 1

    async def _manejar_mensajes(self) -> None:
        """Bucle de mensajes del cliente tras el handshake."""
        while True:
            tipo = (await self._leer_exacto(1))[0]

            if tipo == CLIENT_SET_PIXEL_FORMAT:
                resto = await self._leer_exacto(19)
                self.registrar("SetPixelFormat", bytes([tipo]) + resto)
            elif tipo == CLIENT_SET_ENCODINGS:
                header = await self._leer_exacto(3)
                num_encodings = struct.unpack("!H", header[1:])[0]
                encodings = await self._leer_exacto(num_encodings * 4)
                self.registrar("SetEncodings", bytes([tipo]) + header + encodings)
            elif tipo == CLIENT_FRAMEBUFFER_UPDATE_REQUEST:
                resto = await self._leer_exacto(9)
                self.registrar("FramebufferUpdateRequest", bytes([tipo]) + resto)
                await self._enviar_framebuffer_update()
            elif tipo == CLIENT_KEY_EVENT:
                resto = await self._leer_exacto(7)
                self.registrar("KeyEvent", bytes([tipo]) + resto)
            elif tipo == CLIENT_POINTER_EVENT:
                resto = await self._leer_exacto(5)
                self.registrar("PointerEvent", bytes([tipo]) + resto)
                if resto[0] == 0:
                    self._t_pointer_up = time.monotonic()
            elif tipo == CLIENT_CUT_TEXT:
                header = await self._leer_exacto(7)
                largo = struct.unpack("!I", header[3:])[0]
                texto = await self._leer_exacto(largo)
                self.registrar("ClientCutText", bytes([tipo]) + header + texto)
            else:
                logger.warning("Tipo de mensaje desconocido: %s", tipo)

    async def _handler(self, websocket: ServerConnection) -> None:
        """Handler de cada conexión WebSocket."""
        self._websocket = websocket
        self._handshake_completado.clear()
        self._indice_pantalla = 0
        self._contador_distintas = 0
        self._updates_servidos = 0
        self._t_pointer_up = None
        self._buzon = bytearray()
        self.mensajes_ws = []
        try:
            self.subprotocol_solicitado = websocket.request.headers.get("Sec-WebSocket-Protocol", "")
            if self.config.nunca_saludar:
                # C33: acepta la conexión y nunca contesta el saludo;
                # termina cuando el cliente se desconecta.
                try:
                    await self._websocket.recv()
                except Exception:
                    pass
                return
            try:
                ok = await self._manejar_handshake()
            except Exception as exc:  # conexión cerrada por el cliente
                logger.debug("Handshake terminado: %s", exc)
                return
            if not ok:
                return
            try:
                await self._manejar_mensajes()
            except Exception as exc:  # conexión cerrada por el cliente
                logger.debug("Conexión terminada: %s", exc)
        finally:
            self._cerrado.set()


async def crear_servidor(config: Optional[ConfiguracionServidor] = None) -> ServidorRFBFalso:
    """Crea e inicia un servidor RFB falso."""
    if config is None:
        config = ConfiguracionServidor()
    servidor = ServidorRFBFalso(config)
    await servidor.iniciar()
    return servidor
