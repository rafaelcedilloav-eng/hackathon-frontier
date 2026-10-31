"""Funciones puras del protocolo RFB 3.8: sin red, sin estado, sin secretos en los errores."""

import struct
import zlib

from Crypto.Cipher import DES

# NOTA: constantes de la tabla A; nada de números mágicos dentro de las funciones.
UMBRAL_NEGRO = 16
BITS_POR_BYTE = 8
BYTES_POR_PIXEL = 4
BYTES_POR_PIXEL_RGB = 3
LARGO_CLAVE_VNC = 8
LARGO_DESAFIO = 16
KEYSYM_BASE_UNICODE = 0x01000000
CODIFICACION_RAW = 0
NIVEL_ZLIB = 1

# NOTA: posiciones de los canales dentro de un píxel BGRX y de un píxel RGB.
POSICION_CANAL_AZUL = 0
POSICION_CANAL_VERDE = 1
POSICION_CANAL_ROJO = 2
POSICION_RGB_ROJO = 0
POSICION_RGB_VERDE = 1
POSICION_RGB_AZUL = 2

# NOTA: campos del formato de píxel que fija A20.
BITS_POR_PIXEL_FORMATO = 32
PROFUNDIDAD_COLOR = 24
ORDEN_LITTLE_ENDIAN = 0
COLOR_VERDADERO = 1
MAXIMO_POR_CANAL = 255
DESPLAZAMIENTO_ROJO = 16
DESPLAZAMIENTO_VERDE = 8
DESPLAZAMIENTO_AZUL = 0

# NOTA: tipos de mensaje RFB que este cliente manda (uno por función msg_*).
TIPO_SET_PIXEL_FORMAT = 0
TIPO_SET_ENCODINGS = 2
TIPO_FRAMEBUFFER_REQUEST = 3
TIPO_KEY_EVENT = 4
TIPO_POINTER_EVENT = 5

# NOTA: banderas dentro de los mensajes del cliente.
TECLA_PULSADA = 1
TECLA_SOLTADA = 0
PETICION_COMPLETA = 0
PETICION_INCREMENTAL = 1
RELLENO_CERO = 0
NUM_CODIFICACIONES = 1

# NOTA: constantes del PNG escrito a mano (firma, IHDR y filtro por línea).
PNG_FIRMA = b"\x89PNG\r\n\x1a\n"
PNG_PROFUNDIDAD_BITS = 8
PNG_TIPO_COLOR_RGB = 2
PNG_COMPRESION_DEFLATE = 0
PNG_FILTRO_ADAPTATIVO = 0
PNG_SIN_ENTRELAZADO = 0
PNG_FILTRO_NINGUNO = 0
LARGO_U8 = 1
MASCARA_CRC32 = 0xFFFFFFFF

# NOTA: nombres comunes de tecla aceptados por keysym_de_tecla (en minúsculas).
TECLAS_VALIDAS = {
    "enter": 0xFF0D,
    "return": 0xFF0D,
    "tab": 0xFF09,
    "esc": 0xFF1B,
    "escape": 0xFF1B,
}

# NOTA: tabla de bytes.translate para fraccion_no_negra: 1 si el byte supera UMBRAL_NEGRO.
TABLA_PIXEL_CLARO = bytes(
    (1 if valor > UMBRAL_NEGRO else 0) for valor in range(1 << BITS_POR_BYTE)
)


def _espejar_bits(byte: int) -> int:
    # NOTA: VNC usa el orden de bits del DES manual: 0x61 (0110 0001) -> 0x86 (1000 0110).
    resultado = 0
    for posicion in range(BITS_POR_BYTE):
        resultado = (resultado << 1) | ((byte >> posicion) & 1)
    return resultado


def clave_vnc(password: str) -> bytes:
    # NOTA: clave del desafío VNC: latin-1, 8 bytes rellenados con ceros y bits espejados.
    if not password:
        raise ValueError("la contraseña está vacía")
    try:
        crudo = password.encode("latin-1")
    except UnicodeEncodeError:
        # NOTA: la causa trae el carácter problemático (parte de la contraseña): no se encadena.
        raise ValueError("la contraseña tiene caracteres fuera de latin-1") from None
    crudo = crudo[:LARGO_CLAVE_VNC]
    crudo = crudo + b"\x00" * (LARGO_CLAVE_VNC - len(crudo))
    return bytes(_espejar_bits(byte) for byte in crudo)


def respuesta_desafio(password: str, desafio: bytes) -> bytes:
    # NOTA: respuesta VNC auth: DES-ECB de cada bloque de 8 bytes con la clave de arriba.
    if len(desafio) != LARGO_DESAFIO:
        raise ValueError(f"el desafío debe medir {LARGO_DESAFIO} bytes, no {len(desafio)}")
    cifrador = DES.new(clave_vnc(password), DES.MODE_ECB)
    return cifrador.encrypt(desafio[:LARGO_CLAVE_VNC]) + cifrador.encrypt(desafio[LARGO_CLAVE_VNC:])


def keysym_de_caracter(caracter: str) -> int:
    # NOTA: un carácter imprimible; latin-1 va directo al keysym, el resto a la serie Unicode.
    if len(caracter) != 1:
        raise ValueError("hace falta exactamente un carácter")
    if not caracter.isprintable():
        raise ValueError(f"carácter no imprimible: U+{ord(caracter):04X}")
    try:
        return caracter.encode("latin-1")[0]
    except UnicodeEncodeError:
        return KEYSYM_BASE_UNICODE + ord(caracter)


def keysym_de_tecla(nombre: str) -> int:
    # NOTA: nombre común de tecla -> keysym X11; el error lista los nombres válidos.
    if not nombre or nombre.lower() not in TECLAS_VALIDAS:
        validas = ", ".join(sorted(TECLAS_VALIDAS))
        raise ValueError(f"tecla no soportada: {nombre!r}; válidas: {validas}")
    return TECLAS_VALIDAS[nombre.lower()]


def msg_pointer(mascara: int, x: int, y: int) -> bytes:
    # NOTA: PointerEvent: tipo 5, máscara de botones y posición en u16 big-endian.
    return struct.pack("!BBHH", TIPO_POINTER_EVENT, mascara, x, y)


def msg_key(abajo: bool, keysym: int) -> bytes:
    # NOTA: KeyEvent: tipo 4, bandera de pulsado, 2 de relleno y keysym u32 big-endian.
    return struct.pack("!BBHI", TIPO_KEY_EVENT,
                       TECLA_PULSADA if abajo else TECLA_SOLTADA, RELLENO_CERO, keysym)


def msg_set_pixel_format() -> bytes:
    # NOTA: fija 32 bpp, profundidad 24, little-endian, color verdadero, B,G,R,X.
    tipo_y_relleno = struct.pack("!B3x", TIPO_SET_PIXEL_FORMAT)
    formato = struct.pack(
        "!BBBBHHHBBB3x",
        BITS_POR_PIXEL_FORMATO, PROFUNDIDAD_COLOR, ORDEN_LITTLE_ENDIAN, COLOR_VERDADERO,
        MAXIMO_POR_CANAL, MAXIMO_POR_CANAL, MAXIMO_POR_CANAL,
        DESPLAZAMIENTO_ROJO, DESPLAZAMIENTO_VERDE, DESPLAZAMIENTO_AZUL)
    return tipo_y_relleno + formato


def msg_set_encodings() -> bytes:
    # NOTA: declara un solo códec al servidor: Raw.
    return (struct.pack("!BBH", TIPO_SET_ENCODINGS, RELLENO_CERO, NUM_CODIFICACIONES)
            + struct.pack("!i", CODIFICACION_RAW))


def msg_update_request(incremental: bool, x: int, y: int, ancho: int, alto: int) -> bytes:
    # NOTA: FramebufferUpdateRequest con bandera incremental y rectángulo en u16.
    bandera = PETICION_INCREMENTAL if incremental else PETICION_COMPLETA
    return struct.pack("!BBHHHH", TIPO_FRAMEBUFFER_REQUEST, bandera, x, y, ancho, alto)


def _trozo_png(tipo: bytes, contenido: bytes) -> bytes:
    # NOTA: un chunk PNG: largo u32, tipo, contenido y CRC32.
    return (struct.pack("!I", len(contenido)) + tipo + contenido
            + struct.pack("!I", zlib.crc32(tipo + contenido) & MASCARA_CRC32))


def png_desde_bgrx(bgrx: bytes, ancho: int, alto: int) -> bytes:
    # NOTA: PNG RGB 8 bits armado por rebanadas (sin bucles por píxel) y zlib a NIVEL_ZLIB.
    if len(bgrx) != ancho * alto * BYTES_POR_PIXEL:
        esperado = ancho * alto * BYTES_POR_PIXEL
        raise ValueError(f"el framebuffer debe medir {esperado} bytes, no {len(bgrx)}")
    rgb = bytearray(ancho * alto * BYTES_POR_PIXEL_RGB)
    rgb[POSICION_RGB_ROJO::BYTES_POR_PIXEL_RGB] = bgrx[POSICION_CANAL_ROJO::BYTES_POR_PIXEL]
    rgb[POSICION_RGB_VERDE::BYTES_POR_PIXEL_RGB] = bgrx[POSICION_CANAL_VERDE::BYTES_POR_PIXEL]
    rgb[POSICION_RGB_AZUL::BYTES_POR_PIXEL_RGB] = bgrx[POSICION_CANAL_AZUL::BYTES_POR_PIXEL]
    largo_fila = LARGO_U8 + ancho * BYTES_POR_PIXEL_RGB
    lineas = bytearray(alto * largo_fila)
    for fila in range(alto):
        inicio = fila * largo_fila
        lineas[inicio] = PNG_FILTRO_NINGUNO
        lineas[inicio + LARGO_U8:inicio + largo_fila] = (
            rgb[fila * ancho * BYTES_POR_PIXEL_RGB:(fila + 1) * ancho * BYTES_POR_PIXEL_RGB])
    ihdr = struct.pack("!IIBBBBB", ancho, alto, PNG_PROFUNDIDAD_BITS, PNG_TIPO_COLOR_RGB,
                       PNG_COMPRESION_DEFLATE, PNG_FILTRO_ADAPTATIVO, PNG_SIN_ENTRELAZADO)
    return (PNG_FIRMA + _trozo_png(b"IHDR", ihdr)
            + _trozo_png(b"IDAT", zlib.compress(bytes(lineas), NIVEL_ZLIB))
            + _trozo_png(b"IEND", b""))


def _banderas_claras(canal: bytes) -> int:
    # NOTA: cada byte del canal pasa a 0/1 (si supera UMBRAL_NEGRO) en un entero grande.
    return int.from_bytes(canal.translate(TABLA_PIXEL_CLARO), "big")


def fraccion_no_negra(bgrx: bytes) -> float:
    # NOTA: píxeles claros sin bucle: translate por canal, OR de enteros y bit_count.
    total_pixeles = len(bgrx) // BYTES_POR_PIXEL
    if total_pixeles == 0:
        return 0.0
    pixeles = memoryview(bgrx)[:total_pixeles * BYTES_POR_PIXEL]
    claros = 0
    for posicion in (POSICION_CANAL_AZUL, POSICION_CANAL_VERDE, POSICION_CANAL_ROJO):
        claros |= _banderas_claras(pixeles[posicion::BYTES_POR_PIXEL].tobytes())
    return claros.bit_count() / total_pixeles
