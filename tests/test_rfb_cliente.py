"""
Pruebas de ClienteRFB (Tabla C) contra el servidor RFB falso.

Cada fila de la tabla C es una prueba con el resultado exacto que dice la
tabla. Los valores esperados van literales (no se recalculan con el código
bajo prueba ni con Crypto). No hay pytest-asyncio: se usa asyncio.run dentro
de pruebas normales.
"""
import asyncio
import logging
import struct
import time
import zlib

import pytest

from frontier_agente.rfb_cliente import ClienteRFB
from frontier_agente.errores import (
    ErrorAutenticacion,
    ErrorConfiguracion,
    ErrorConexion,
    ErrorProtocolo,
    ErrorTiempo,
)
from falso_rfb import ConfiguracionServidor, Pantalla, crear_servidor

# Literales de la especificación (tablas A y C).
RESPUESTA_A6 = bytes([
    0xb8, 0x66, 0x92, 0x41, 0x25, 0xc8, 0xee, 0xbb,
    0x9d, 0xeb, 0xc1, 0xdb, 0x61, 0xc5, 0x38, 0xe2,
])
A20_SET_PIXEL_FORMAT = (
    b"\x00\x00\x00\x00"
    b"\x20\x18\x00\x01\x00\xFF\x00\xFF\x00\xFF\x10\x08\x00\x00\x00\x00"
)
A21_SET_ENCODINGS = bytes([0x02, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])
# msg_update_request(False, 0, 0, 64, 48): no incremental, pantalla completa.
A22_AJUSTADA_64x48 = bytes([0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x00, 0x30])

ANCHO_64 = 64
ALTO_48 = 48


# ------------------------------------------------------------- ayudantes
def _pantalla_patron(ancho: int, alto: int) -> Pantalla:
    """Pantalla con un patrón BGRX determinista (B, G y R derivados del índice)."""
    datos = bytearray(ancho * alto * 4)
    for i in range(ancho * alto):
        datos[4 * i] = i & 0xFF           # B
        datos[4 * i + 1] = (i * 7) & 0xFF  # G
        datos[4 * i + 2] = (i * 13) & 0xFF  # R
    return Pantalla(ancho, alto, bytes(datos))


def _pantalla_llena(ancho: int, alto: int, valor: int) -> Pantalla:
    """Pantalla con todos los bytes BGRX iguales a valor."""
    return Pantalla(ancho, alto, bytes([valor]) * (ancho * alto * 4))


def _rgb_de_bgrx(datos: bytes, n: int) -> list:
    """Convierte n píxeles BGRX a lista de tuplas RGB."""
    return [(datos[4 * i + 2], datos[4 * i + 1], datos[4 * i]) for i in range(n)]


def _decodificar_png_rgb(png: bytes):
    """NOTA: decodificador de PNG mínimo para pruebas (sin Pillow): firma,
    chunks con CRC, IHDR RGB de 8 bits, IDAT con zlib, filtro 0. Devuelve
    (ancho, alto, pixeles RGB)."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "firma PNG incorrecta"
    chunks = []
    pos = 8
    while pos < len(png):
        (largo,) = struct.unpack("!I", png[pos:pos + 4])
        tipo = png[pos + 4:pos + 8]
        datos = png[pos + 8:pos + 8 + largo]
        assert len(datos) == largo, "chunk truncado"
        (crc,) = struct.unpack("!I", png[pos + 8 + largo:pos + 12 + largo])
        assert crc == zlib.crc32(tipo + datos) & 0xFFFFFFFF, f"CRC inválido en {tipo}"
        chunks.append((tipo, datos))
        pos += 12 + largo
    assert chunks[-1][0] == b"IEND", "falta IEND"

    (ihdr,) = [d for t, d in chunks if t == b"IHDR"]
    ancho, alto, profundidad, tipo_color = struct.unpack("!IIBB", ihdr[:10])
    assert (profundidad, tipo_color) == (8, 2), "IHDR debe ser 8 bits RGB"
    idat = b"".join(d for t, d in chunks if t == b"IDAT")
    crudo = zlib.decompress(idat)
    assert len(crudo) == alto * (1 + ancho * 3), "IDAT con tamaño inesperado"

    pixeles = []
    for fila in range(alto):
        desplaz = fila * (1 + ancho * 3)
        assert crudo[desplaz] == 0, "filtro de scanline distinto de 0"
        for col in range(ancho):
            base = desplaz + 1 + col * 3
            pixeles.append((crudo[base], crudo[base + 1], crudo[base + 2]))
    return ancho, alto, pixeles


async def _esperar_condicion(cond, timeout: float = 5.0) -> bool:
    """Espera a que cond() sea verdadera, sondeando cada 20 ms."""
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if cond():
            return True
        await asyncio.sleep(0.02)
    return cond()


def _key_events(servidor) -> list:
    """[(down, keysym)] de cada KeyEvent recibido, en orden."""
    return [(r.datos[1], int.from_bytes(r.datos[4:8], "big"))
            for r in servidor.registros_de("KeyEvent")]


def _pointer_events(servidor) -> list:
    """[(mascara, x, y)] de cada PointerEvent recibido, en orden."""
    return [(r.datos[1], int.from_bytes(r.datos[2:4], "big"), int.from_bytes(r.datos[4:6], "big"))
            for r in servidor.registros_de("PointerEvent")]


# ------------------------------------------------------------ C1 a C5
def test_C1_handshake_con_password_correcta():
    """C1: el servidor recibe la respuesta de A6; ancho/alto son los de su
    ServerInit; no hay excepción."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                assert (c.ancho, c.alto) == (ANCHO_64, ALTO_48)
            # Lo que el cliente respondió durante el handshake (prosa 2).
            version = servidor.registros_de("ClientVersion")
            assert len(version) == 1
            assert version[0].datos == b"RFB 003.008\n"
            tipo = servidor.registros_de("SecurityType")
            assert len(tipo) == 1
            assert tipo[0].datos == bytes([0x02])
            client_init = servidor.registros_de("ClientInit")
            assert len(client_init) == 1
            assert client_init[0].datos == bytes([0x01])  # shared = 1
            # La respuesta al desafío es exactamente la de A6 (literal).
            respuestas = servidor.registros_de("ChallengeResponse")
            assert len(respuestas) == 1
            assert respuestas[0].datos == RESPUESTA_A6
            # Conecta con subprotocolo "binary" (prosa 1).
            assert "binary" in servidor.subprotocol_solicitado
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C2_password_equivocada():
    """C2: ErrorAutenticacion; la contraseña no aparece en str(exc);
    el WebSocket queda cerrado."""
    async def cuerpo():
        servidor = await crear_servidor()  # espera "password"
        try:
            with pytest.raises(ErrorAutenticacion) as excinfo:
                async with ClienteRFB(servidor.url, "clave-equivocada-XYZ"):
                    pass
            assert "clave-equivocada-XYZ" not in str(excinfo.value)
            assert await servidor.esperar_cierre(timeout=2.0)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C3_solo_tipo_1_sin_auth():
    """C3: el servidor ofrece solo el tipo 1 -> ErrorProtocolo."""
    async def cuerpo():
        config = ConfiguracionServidor(tipos_seguridad=[1])
        servidor = await crear_servidor(config)
        try:
            with pytest.raises(ErrorProtocolo):
                async with ClienteRFB(servidor.url, "password"):
                    pass
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C4_cero_tipos_con_razon():
    """C4: 0 tipos con razón "too many" -> ErrorProtocolo con "too many"."""
    async def cuerpo():
        config = ConfiguracionServidor(tipos_seguridad=[], razon_sin_tipos="too many")
        servidor = await crear_servidor(config)
        try:
            with pytest.raises(ErrorProtocolo) as excinfo:
                async with ClienteRFB(servidor.url, "password"):
                    pass
            assert "too many" in str(excinfo.value)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C5_version_3_3():
    """C5: el servidor dice RFB 003.003 -> ErrorProtocolo."""
    async def cuerpo():
        config = ConfiguracionServidor(version_rfb=b"RFB 003.003\n")
        servidor = await crear_servidor(config)
        try:
            with pytest.raises(ErrorProtocolo):
                async with ClienteRFB(servidor.url, "password"):
                    pass
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# ----------------------------------------------------------------- C6 a C9
def test_C6_orden_de_mensajes_tras_handshake():
    """C6: primero SetPixelFormat (A20), luego SetEncodings (A21), y solo
    luego un FramebufferUpdateRequest."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                assert await servidor.esperar_handshake()
                ok = await _esperar_condicion(
                    lambda: servidor.registros_de("SetPixelFormat")
                    and servidor.registros_de("SetEncodings"))
                assert ok, "no llegaron SetPixelFormat y SetEncodings"
                spf = servidor.registros_de("SetPixelFormat")[0]
                se = servidor.registros_de("SetEncodings")[0]
                assert spf.datos == A20_SET_PIXEL_FORMAT
                assert se.datos == A21_SET_ENCODINGS
                assert servidor.registros.index(spf) < servidor.registros.index(se)
                # Antes de pedir una captura no hay ninguna petición de update.
                assert servidor.registros_de("FramebufferUpdateRequest") == []
                await c.captura()
                ok = await _esperar_condicion(
                    lambda: bool(servidor.registros_de("FramebufferUpdateRequest")))
                assert ok, "no llegó el FramebufferUpdateRequest"
                for r in servidor.registros_de("FramebufferUpdateRequest"):
                    assert servidor.registros.index(r) > servidor.registros.index(se)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C7_captura_un_rectangulo_raw():
    """C7: PNG con los píxeles exactos del servidor; la petición es A22
    ajustada al tamaño (no incremental, pantalla completa)."""
    async def cuerpo():
        pantalla = _pantalla_patron(ANCHO_64, ALTO_48)
        servidor = await crear_servidor(ConfiguracionServidor(pantallas=[pantalla]))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                png = await c.captura()
            ancho, alto, pixeles = _decodificar_png_rgb(png)
            assert (ancho, alto) == (ANCHO_64, ALTO_48)
            assert pixeles == _rgb_de_bgrx(pantalla.datos_bgrx, ANCHO_64 * ALTO_48)
            peticiones = servidor.registros_de("FramebufferUpdateRequest")
            assert len(peticiones) >= 1
            assert peticiones[0].datos == A22_AJUSTADA_64x48
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C8_captura_2_rectangulos_bell_y_cuttext():
    """C8: pantalla en 2 rectángulos con un Bell y un ServerCutText("hola")
    antes del update; una segunda captura() también sale bien."""
    async def cuerpo():
        pantalla = _pantalla_patron(ANCHO_64, ALTO_48)
        config = ConfiguracionServidor(
            pantallas=[pantalla], insertar_bell_y_cuttext=True, dos_rectangulos=True)
        servidor = await crear_servidor(config)
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                for _ in range(2):
                    png = await c.captura()
                    ancho, alto, pixeles = _decodificar_png_rgb(png)
                    assert (ancho, alto) == (ANCHO_64, ALTO_48)
                    assert pixeles == _rgb_de_bgrx(pantalla.datos_bgrx, ANCHO_64 * ALTO_48)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C9_flujo_fragmentado_de_1_byte():
    """C9: todo el flujo de 1 byte por mensaje WebSocket (pantalla 8x6):
    handshake y captura() correctos."""
    async def cuerpo():
        pantalla = _pantalla_patron(8, 6)
        config = ConfiguracionServidor(pantallas=[pantalla], fragmentar_1_byte=True)
        servidor = await crear_servidor(config)
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                assert (c.ancho, c.alto) == (8, 6)
                png = await c.captura()
            ancho, alto, pixeles = _decodificar_png_rgb(png)
            assert (ancho, alto) == (8, 6)
            assert pixeles == _rgb_de_bgrx(pantalla.datos_bgrx, 8 * 6)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# --------------------------------------------------------------- C10 a C12
def test_C10_sin_respuesta_error_tiempo():
    """C10: el servidor nunca contesta; tope_lectura_s=0.5 -> ErrorTiempo
    en menos de 2 s."""
    async def cuerpo():
        config = ConfiguracionServidor(modo_respuesta="no_responder")
        servidor = await crear_servidor(config)
        try:
            t0 = time.monotonic()
            with pytest.raises(ErrorTiempo):
                async with ClienteRFB(servidor.url, "password", tope_lectura_s=0.5) as c:
                    await c.captura()
            assert time.monotonic() - t0 < 2.0
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C11_tipo_de_mensaje_99():
    """C11: el servidor manda un mensaje de tipo 99 -> ErrorProtocolo."""
    async def cuerpo():
        config = ConfiguracionServidor(modo_respuesta="tipo_99")
        servidor = await crear_servidor(config)
        try:
            with pytest.raises(ErrorProtocolo):
                async with ClienteRFB(servidor.url, "password") as c:
                    await c.captura()
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C12_rectangulo_encoding_tight():
    """C12: un rectángulo con codificación 7 (Tight) -> ErrorProtocolo."""
    async def cuerpo():
        config = ConfiguracionServidor(modo_respuesta="encoding_7")
        servidor = await crear_servidor(config)
        try:
            with pytest.raises(ErrorProtocolo):
                async with ClienteRFB(servidor.url, "password") as c:
                    await c.captura()
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# --------------------------------------------------------------- C13 a C14
def test_C13_clic_tres_pointer_events():
    """C13: clic(100, 20) -> 3 PointerEvent con máscaras 0, 1, 0 en (100, 20);
    entre bajar y soltar pasan >= 0.150 s y <= 0.350 s."""
    async def cuerpo():
        # Pantalla 128x96 para que (100, 20) esté dentro del rango.
        pantalla = _pantalla_llena(128, 96, 0x40)
        servidor = await crear_servidor(ConfiguracionServidor(pantallas=[pantalla]))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.clic(100, 20)
            ok = await _esperar_condicion(
                lambda: len(servidor.registros_de("PointerEvent")) >= 3)
            assert ok, "no llegaron los 3 PointerEvent"
            eventos = servidor.registros_de("PointerEvent")
            assert len(eventos) == 3
            assert _pointer_events(servidor) == [(0, 100, 20), (1, 100, 20), (0, 100, 20)]
            entre_bajar_y_soltar = eventos[2].timestamp - eventos[1].timestamp
            assert 0.150 <= entre_bajar_y_soltar <= 0.350
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C14_clic_fuera_de_rango():
    """C14: clic(-1, 5), clic(64, 5), clic(5, 48) en pantalla 64x48 ->
    ValueError y ningún PointerEvent recibido."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                for x, y in [(-1, 5), (64, 5), (5, 48)]:
                    with pytest.raises(ValueError):
                        await c.clic(x, y)
                await asyncio.sleep(0.2)
            assert servidor.registros_de("PointerEvent") == []
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# --------------------------------------------------------------- C15 a C19
def test_C15_escribir_hola():
    """C15: escribir("Hola") -> FFE3↓ 61↓ 61↑ FFE3↑ 48↓ 48↑ 6F↓ 6F↑ 6C↓ 6C↑ 61↓ 61↑."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.escribir("Hola")
            ok = await _esperar_condicion(lambda: len(_key_events(servidor)) >= 12)
            assert ok, "no llegaron los 12 KeyEvent"
            assert _key_events(servidor) == [
                (1, 0xFFE3), (1, 0x61), (0, 0x61), (0, 0xFFE3),
                (1, 0x48), (0, 0x48),
                (1, 0x6F), (0, 0x6F),
                (1, 0x6C), (0, 0x6C),
                (1, 0x61), (0, 0x61),
            ]
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C16_escribir_eniandu():
    """C16: escribir("Ñandú") -> tras el Ctrl+A, keysyms D1 61 6E 64 FA."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.escribir("Ñandú")
            ok = await _esperar_condicion(lambda: len(_key_events(servidor)) >= 14)
            assert ok, "no llegaron los 14 KeyEvent"
            tras_ctrl_a = _key_events(servidor)[4:]
            assert tras_ctrl_a == [
                (1, 0xD1), (0, 0xD1),
                (1, 0x61), (0, 0x61),
                (1, 0x6E), (0, 0x6E),
                (1, 0x64), (0, 0x64),
                (1, 0xFA), (0, 0xFA),
            ]
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C17_escribir_normaliza_nfc():
    """C17: escribir("e\\u0301") -> tras el Ctrl+A, un solo carácter: E9."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.escribir("é")
            ok = await _esperar_condicion(lambda: len(_key_events(servidor)) >= 6)
            assert ok, "no llegaron los 6 KeyEvent"
            tras_ctrl_a = _key_events(servidor)[4:]
            assert tras_ctrl_a == [(1, 0xE9), (0, 0xE9)]
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C18_escribir_euro():
    """C18: escribir("€") -> tras el Ctrl+A, 010020AC abajo y arriba."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.escribir("€")
            ok = await _esperar_condicion(lambda: len(_key_events(servidor)) >= 6)
            assert ok, "no llegaron los 6 KeyEvent"
            tras_ctrl_a = _key_events(servidor)[4:]
            assert tras_ctrl_a == [(1, 0x010020AC), (0, 0x010020AC)]
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C19_escribir_invalido_no_manda_nada():
    """C19: escribir("") y escribir("a\\nb") -> ValueError y ningún KeyEvent
    (ni el Ctrl+A)."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                with pytest.raises(ValueError):
                    await c.escribir("")
                with pytest.raises(ValueError):
                    await c.escribir("a\nb")
                await asyncio.sleep(0.2)
            assert servidor.registros_de("KeyEvent") == []
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# --------------------------------------------------------------- C20 a C21
def test_C20_tecla_enter_tab_esc():
    """C20: tecla("Enter"), ("Tab"), ("Esc") -> FF0D, FF09, FF1B, cada una
    abajo y luego arriba."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.tecla("Enter")
                await c.tecla("Tab")
                await c.tecla("Esc")
            ok = await _esperar_condicion(lambda: len(_key_events(servidor)) >= 6)
            assert ok, "no llegaron los 6 KeyEvent"
            assert _key_events(servidor) == [
                (1, 0xFF0D), (0, 0xFF0D),
                (1, 0xFF09), (0, 0xFF09),
                (1, 0xFF1B), (0, 0xFF1B),
            ]
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C21_tecla_invalida_no_manda_nada():
    """C21: tecla("F13") -> ValueError y ningún KeyEvent."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                with pytest.raises(ValueError):
                    await c.tecla("F13")
                await asyncio.sleep(0.2)
            assert servidor.registros_de("KeyEvent") == []
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# ----------------------------------------------------------------- C31
def test_C31_un_mensaje_rfb_un_mensaje_websocket():
    """C31: tras un handshake bueno, clic(5, 5) y tecla("Enter"): cada
    PointerEvent llega como UN mensaje WebSocket de 6 bytes, cada KeyEvent
    como uno de 8, y SetPixelFormat como uno de 20 (prosa 10)."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.clic(5, 5)
                await c.tecla("Enter")
            ok = await _esperar_condicion(
                lambda: len(_pointer_events(servidor)) >= 3
                and len(_key_events(servidor)) >= 2)
            assert ok, "no llegaron todos los eventos"
            mensajes = servidor.mensajes_ws
            # SetPixelFormat: un único mensaje de 20 bytes con el literal A20.
            spf = [m for m in mensajes if len(m) == 20 and m[0] == 0x00]
            assert spf == [A20_SET_PIXEL_FORMAT]
            # Cada PointerEvent: un mensaje de 6 bytes (máscaras 0, 1, 0 en (5, 5)).
            pointers = [m for m in mensajes if len(m) == 6 and m[0] == 0x05]
            assert pointers == [
                bytes([0x05, 0x00, 0x00, 0x05, 0x00, 0x05]),
                bytes([0x05, 0x01, 0x00, 0x05, 0x00, 0x05]),
                bytes([0x05, 0x00, 0x00, 0x05, 0x00, 0x05]),
            ]
            # Cada KeyEvent: un mensaje de 8 bytes (Enter abajo y arriba).
            keys = [m for m in mensajes if len(m) == 8 and m[0] == 0x04]
            assert keys == [
                bytes([0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x0D]),
                bytes([0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x0D]),
            ]
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# --------------------------------------------------------------- C22 a C25
def test_C22_esperar_quieta_pantalla_fija():
    """C22: pantalla fija, sin acción previa -> (True, png) con exactamente
    2 peticiones de captura y menos de 1.0 s."""
    async def cuerpo():
        pantalla = _pantalla_patron(ANCHO_64, ALTO_48)
        servidor = await crear_servidor(ConfiguracionServidor(pantallas=[pantalla]))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                t0 = time.monotonic()
                quieta, png = await c.esperar_quieta()
                transcurrido = time.monotonic() - t0
            assert quieta is True
            assert len(servidor.registros_de("FramebufferUpdateRequest")) == 2
            assert transcurrido < 1.0
            _, _, pixeles = _decodificar_png_rgb(png)
            assert pixeles == _rgb_de_bgrx(pantalla.datos_bgrx, ANCHO_64 * ALTO_48)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C23_esperar_quieta_secuencia_abcd():
    """C23: pantallas A, B, C en las peticiones 1, 2 y 3; desde la 4 en
    adelante siempre D -> (True, png de D) con exactamente 5 peticiones,
    separadas entre sí por al menos 0.2 s."""
    async def cuerpo():
        pantallas = [_pantalla_llena(ANCHO_64, ALTO_48, v) for v in (0x11, 0x22, 0x33, 0x44)]
        servidor = await crear_servidor(ConfiguracionServidor(pantallas=pantallas))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                quieta, png = await c.esperar_quieta()
            assert quieta is True
            peticiones = servidor.registros_de("FramebufferUpdateRequest")
            assert len(peticiones) == 5
            # Cada petición separada de la anterior por al menos 0.2 s.
            for anterior, actual in zip(peticiones, peticiones[1:]):
                assert actual.timestamp - anterior.timestamp >= 0.2
            _, _, pixeles = _decodificar_png_rgb(png)
            # D: todos los bytes BGRX en 0x44 -> RGB (68, 68, 68).
            assert pixeles == [(0x44, 0x44, 0x44)] * (ANCHO_64 * ALTO_48)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C24_esperar_quieta_nunca_quieta():
    """C24: cada petición recibe una pantalla distinta -> (False, png de la
    última capturada); tarda entre 2.8 y 4.0 s."""
    async def cuerpo():
        base = _pantalla_llena(ANCHO_64, ALTO_48, 0x00)
        servidor = await crear_servidor(
            ConfiguracionServidor(pantallas=[base], generar_distintas=True))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                t0 = time.monotonic()
                quieta, png = await c.esperar_quieta()
                transcurrido = time.monotonic() - t0
            assert quieta is False
            assert 2.8 <= transcurrido <= 4.0
            peticiones = servidor.registros_de("FramebufferUpdateRequest")
            assert len(peticiones) >= 2
            # La última pantalla servida lleva el contador de la última petición.
            _, _, pixeles = _decodificar_png_rgb(png)
            ultimo = (len(peticiones) - 1) & 0xFF
            assert pixeles[0] == (0, 0, ultimo)
            assert pixeles[1:] == [(0, 0, 0)] * (len(pixeles) - 1)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C25_esperar_quieta_tras_clic_con_repintado():
    """C25: clic y de inmediato esperar_quieta(); el servidor sirve V hasta
    0.8 s después del pointer-up y luego N -> (True, png de N); ninguna
    petición antes de 0.95 s tras el pointer-up; exactamente 2 peticiones."""
    async def cuerpo():
        vieja = _pantalla_llena(ANCHO_64, ALTO_48, 0x00)   # V: negra
        nueva = _pantalla_llena(ANCHO_64, ALTO_48, 0xAA)   # N: gris
        config = ConfiguracionServidor(pantallas=[vieja, nueva],
                                       cambiar_tras_pointer_up_s=0.8)
        servidor = await crear_servidor(config)
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.clic(5, 5)
                quieta, png = await c.esperar_quieta()
            assert quieta is True
            peticiones = servidor.registros_de("FramebufferUpdateRequest")
            assert len(peticiones) == 2
            pointers = servidor.registros_de("PointerEvent")
            assert len(pointers) == 3
            t_pointer_up = pointers[2].timestamp  # el soltar (máscara 0)
            for r in peticiones:
                assert r.timestamp >= t_pointer_up + 0.95
            _, _, pixeles = _decodificar_png_rgb(png)
            assert pixeles == [(0xAA, 0xAA, 0xAA)] * (ANCHO_64 * ALTO_48)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# --------------------------------------------------------------- C26 a C27
def test_C26_excepcion_dentro_de_async_with():
    """C26: async with y dentro se lanza RuntimeError("x") -> la excepción
    sale; el servidor ve el WebSocket cerrado en menos de 1 s."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            with pytest.raises(RuntimeError):
                async with ClienteRFB(servidor.url, "password"):
                    raise RuntimeError("x")
            assert await servidor.esperar_cierre(timeout=1.0)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C27_cerrar_idempotente_y_metodos_posteriores():
    """C27: cerrar() dos veces; luego captura() -> la segunda cerrar() no
    falla; captura() lanza ErrorConexion sin colgarse."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.cerrar()
                await c.cerrar()
                with pytest.raises(ErrorConexion):
                    await asyncio.wait_for(c.captura(), timeout=3.0)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# --------------------------------------------------------------- C28
def test_C28_ningun_secreto_en_logs_ni_excepciones(caplog):
    """C28: con caplog en DEBUG, tras conectar, captura, clic, escribir, un
    fallo de lectura y cerrar, la contraseña no aparece en ningún log, ni en
    repr(c), ni en str de ninguna excepción."""
    contraseña = "Zeta-9981-Prueba"

    async def cuerpo():
        config = ConfiguracionServidor(password=contraseña, acepta_cualquiera=True,
                                       actualizaciones_maximas=1)
        servidor = await crear_servidor(config)
        try:
            mensajes_error = []
            with caplog.at_level(logging.DEBUG):
                async with ClienteRFB(servidor.url, contraseña,
                                      tope_lectura_s=0.5) as c:
                    await c.captura()
                    await c.clic(5, 5)
                    await c.escribir("hola")
                    try:
                        await c.captura()  # ya no responde: fallo de lectura
                    except Exception as exc:
                        mensajes_error.append(str(exc))
                    assert contraseña not in repr(c)
                    await c.cerrar()
            for mensaje in mensajes_error:
                assert contraseña not in mensaje
            assert contraseña not in caplog.text
        finally:
            await servidor.cerrar()

    asyncio.run(cuerpo())


# --------------------------------------------------------------- C29
def test_C29_desde_entorno_con_dos_variables(monkeypatch):
    """C29: con las dos variables puestas, desde_entorno() da un cliente
    listo para conectar."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            monkeypatch.setenv("FRONTIER_ESCRITORIO_URL", servidor.url)
            monkeypatch.setenv("FRONTIER_ESCRITORIO_PASS", "password")
            cliente = ClienteRFB.desde_entorno()
            async with cliente as c:
                assert (c.ancho, c.alto) == (ANCHO_64, ALTO_48)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C29_desde_entorno_sin_pass(monkeypatch):
    """C29: sin FRONTIER_ESCRITORIO_PASS -> ErrorConfiguracion y el mensaje
    contiene FRONTIER_ESCRITORIO_PASS."""
    monkeypatch.setenv("FRONTIER_ESCRITORIO_URL", "ws://127.0.0.1:1/websockify")
    monkeypatch.delenv("FRONTIER_ESCRITORIO_PASS", raising=False)
    with pytest.raises(ErrorConfiguracion) as excinfo:
        ClienteRFB.desde_entorno()
    assert "FRONTIER_ESCRITORIO_PASS" in str(excinfo.value)


def test_C29_desde_entorno_sin_url(monkeypatch):
    """Caso de borde de la prosa (C29: "sin una de las variables"): sin
    FRONTIER_ESCRITORIO_URL -> ErrorConfiguracion que nombra la variable."""
    monkeypatch.delenv("FRONTIER_ESCRITORIO_URL", raising=False)
    monkeypatch.setenv("FRONTIER_ESCRITORIO_PASS", "password")
    with pytest.raises(ErrorConfiguracion) as excinfo:
        ClienteRFB.desde_entorno()
    assert "FRONTIER_ESCRITORIO_URL" in str(excinfo.value)


# --------------------------------------------------------------- C32 a C36
def test_C32_esperar_quieta_tras_clic_nunca_quieta():
    """C32: clic(5, 5) y de inmediato esperar_quieta() con una pantalla
    distinta en cada petición -> (False, png de la última); pasan entre
    2.8 y 3.6 s desde la llamada (el tope de 3.0 s incluye la espera del
    repintado, no se suma a ella)."""
    async def cuerpo():
        base = _pantalla_llena(ANCHO_64, ALTO_48, 0x00)
        servidor = await crear_servidor(
            ConfiguracionServidor(pantallas=[base], generar_distintas=True))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.clic(5, 5)
                t0 = time.monotonic()
                quieta, png = await c.esperar_quieta()
                transcurrido = time.monotonic() - t0
            assert quieta is False
            assert 2.8 <= transcurrido <= 3.6
            peticiones = servidor.registros_de("FramebufferUpdateRequest")
            assert len(peticiones) >= 2
            _, _, pixeles = _decodificar_png_rgb(png)
            ultimo = (len(peticiones) - 1) & 0xFF
            assert pixeles[0] == (0, 0, ultimo)
            assert pixeles[1:] == [(0, 0, 0)] * (len(pixeles) - 1)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C33_conectar_cancelado_cierra_websocket():
    """C33: el servidor acepta el WebSocket pero nunca contesta el saludo;
    la prueba cancela conectar() a los 0.3 s (asyncio.wait_for) -> el servidor
    ve el WebSocket cerrado en menos de 1 s."""
    async def cuerpo():
        servidor = await crear_servidor(ConfiguracionServidor(nunca_saludar=True))
        try:
            c = ClienteRFB(servidor.url, "password")
            termino = False
            try:
                await asyncio.wait_for(c.conectar(), timeout=0.3)
                termino = True
            except Exception:
                pass  # TimeoutError o el error propio del cliente al cancelarse
            assert not termino, "conectar() retornó sin saludo del servidor"
            assert await servidor.esperar_cierre(timeout=1.0), \
                "el servidor no vio el WebSocket cerrado en menos de 1 s"
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C34_mensaje_de_texto_a_mitad_de_captura():
    """C34: el servidor manda un mensaje WebSocket de TEXTO (no binario)
    con ñ€ a mitad de una captura -> ErrorProtocolo (no UnicodeEncodeError)."""
    async def cuerpo():
        pantalla = _pantalla_patron(ANCHO_64, ALTO_48)
        config = ConfiguracionServidor(pantallas=[pantalla], texto_inesperado="ñ€")
        servidor = await crear_servidor(config)
        try:
            with pytest.raises(ErrorProtocolo):
                async with ClienteRFB(servidor.url, "password") as c:
                    await c.captura()
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C35_tras_error_tiempo_cierra_y_error_conexion():
    """C35: tras un ErrorTiempo (como C10) el cliente cerró la conexión:
    captura() lanza ErrorConexion y el servidor ve el WebSocket cerrado en
    menos de 1 s."""
    async def cuerpo():
        servidor = await crear_servidor(
            ConfiguracionServidor(modo_respuesta="no_responder"))
        try:
            async with ClienteRFB(servidor.url, "password", tope_lectura_s=0.5) as c:
                with pytest.raises(ErrorTiempo):
                    await c.captura()
                assert await servidor.esperar_cierre(timeout=1.0), \
                    "el servidor no vio el WebSocket cerrado en menos de 1 s"
                with pytest.raises(ErrorConexion):
                    await asyncio.wait_for(c.captura(), timeout=3.0)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C37_set_colour_map_entries_antes_del_update():
    """C37: el servidor manda un SetColourMapEntries (tipo 1: 1 byte de
    relleno, primer color u16, cantidad u16 = 2, y 2 colores de 6 bytes)
    justo antes del FramebufferUpdate -> captura() correcta y el cliente
    sigue sincronizado (una segunda captura() también sale bien)."""
    async def cuerpo():
        pantalla = _pantalla_patron(ANCHO_64, ALTO_48)
        config = ConfiguracionServidor(pantallas=[pantalla],
                                       insertar_set_colour_map=True)
        servidor = await crear_servidor(config)
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                for _ in range(2):
                    png = await c.captura()
                    ancho, alto, pixeles = _decodificar_png_rgb(png)
                    assert (ancho, alto) == (ANCHO_64, ALTO_48)
                    assert pixeles == _rgb_de_bgrx(pantalla.datos_bgrx,
                                                   ANCHO_64 * ALTO_48)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_C36_captura_pantalla_completa_rapida():
    """C36: captura() de una pantalla de 1280×800 contra el servidor falso
    -> el PNG llega bien y la llamada tarda menos de 1.5 s."""
    async def cuerpo():
        pantalla = _pantalla_llena(1280, 800, 0x37)
        servidor = await crear_servidor(ConfiguracionServidor(pantallas=[pantalla]))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                assert (c.ancho, c.alto) == (1280, 800)
                t0 = time.monotonic()
                png = await c.captura()
                transcurrido = time.monotonic() - t0
            assert transcurrido < 1.5, f"captura() tardó {transcurrido:.3f} s"
            ancho, alto, pixeles = _decodificar_png_rgb(png)
            assert (ancho, alto) == (1280, 800)
            assert pixeles == [(0x37, 0x37, 0x37)] * (1280 * 800)
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


# ------------------------------------------------ Bloque 6 (tabla R2C del encargo 008)

def test_R2C_1_desplazar_abajo_dos_veces():
    """R2C.1: desplazar(640, 400, True, 2) en pantalla 1280×800 -> por cada
    vez dos PointerEvent (máscara 0x10 y luego máscara 0, ambos en (640, 400));
    4 eventos en total; entre bajar y soltar pasa la pausa de rueda (0.06 s)."""
    async def cuerpo():
        pantalla = _pantalla_llena(1280, 800, 0x40)
        servidor = await crear_servidor(ConfiguracionServidor(pantallas=[pantalla]))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.desplazar(640, 400, True, 2)
            ok = await _esperar_condicion(
                lambda: len(servidor.registros_de("PointerEvent")) >= 4)
            assert ok, "no llegaron los 4 PointerEvent"
            eventos = servidor.registros_de("PointerEvent")
            assert len(eventos) == 4
            assert _pointer_events(servidor) == [
                (0x10, 640, 400), (0, 640, 400),
                (0x10, 640, 400), (0, 640, 400),
            ]
            for vez in range(2):
                pausa = eventos[2 * vez + 1].timestamp - eventos[2 * vez].timestamp
                assert 0.03 <= pausa <= 1.0, f"pausa de rueda inesperada en la vez {vez}"
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_R2C_2_desplazar_arriba_una_vez():
    """R2C.2: desplazar(640, 400, False, 1) -> máscara 0x08 y luego máscara 0."""
    async def cuerpo():
        pantalla = _pantalla_llena(1280, 800, 0x40)
        servidor = await crear_servidor(ConfiguracionServidor(pantallas=[pantalla]))
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                await c.desplazar(640, 400, False, 1)
            ok = await _esperar_condicion(
                lambda: len(servidor.registros_de("PointerEvent")) >= 2)
            assert ok, "no llegaron los 2 PointerEvent"
            assert _pointer_events(servidor) == [(0x08, 640, 400), (0, 640, 400)]
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())


def test_R2C_3_desplazar_invalido_no_manda_nada():
    """R2C.3: desplazar(-1, 5, True) y desplazar(5, 5, True, 0) -> ValueError
    y el servidor no recibió ningún PointerEvent."""
    async def cuerpo():
        servidor = await crear_servidor()
        try:
            async with ClienteRFB(servidor.url, "password") as c:
                with pytest.raises(ValueError):
                    await c.desplazar(-1, 5, True)
                with pytest.raises(ValueError):
                    await c.desplazar(5, 5, True, 0)
                await asyncio.sleep(0.2)
            assert servidor.registros_de("PointerEvent") == []
        finally:
            await servidor.cerrar()
    asyncio.run(cuerpo())
