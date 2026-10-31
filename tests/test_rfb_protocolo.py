"""
Pruebas para las funciones puras de rfb_protocolo.py (Tablas A).
"""
import os
import time

import pytest
from frontier_agente.rfb_protocolo import (
    clave_vnc,
    respuesta_desafio,
    keysym_de_caracter,
    keysym_de_tecla,
    msg_pointer,
    msg_key,
    msg_set_pixel_format,
    msg_set_encodings,
    msg_update_request,
    png_desde_bgrx,
    fraccion_no_negra,
    UMBRAL_NEGRO,
)


class TestClaveVNC:
    """Pruebas A1-A5: clave_vnc"""

    def test_A1_clave_vnc_un_caracter(self):
        """A1: clave_vnc("a") = 86 00 00 00 00 00 00 00"""
        resultado = clave_vnc("a")
        assert resultado == bytes([0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    def test_A2_clave_vnc_password(self):
        """A2: clave_vnc("password") = 0e 86 ce ce ee f6 4e 26"""
        resultado = clave_vnc("password")
        assert resultado == bytes([0x0e, 0x86, 0xce, 0xce, 0xee, 0xf6, 0x4e, 0x26])

    def test_A3_clave_vnc_truncada_a_8(self):
        """A3: clave_vnc("abcdefghij") == clave_vnc("abcdefgh") = 86 46 c6 26 a6 66 e6 16"""
        resultado_largo = clave_vnc("abcdefghij")
        resultado_corto = clave_vnc("abcdefgh")
        esperado = bytes([0x86, 0x46, 0xc6, 0x26, 0xA6, 0x66, 0xe6, 0x16])
        assert resultado_largo == esperado
        assert resultado_corto == esperado
        assert resultado_largo == resultado_corto

    def test_A4_clave_vnc_vacia_lanza_valueerror(self):
        """A4: clave_vnc("") lanza ValueError"""
        with pytest.raises(ValueError):
            clave_vnc("")

    def test_A5_clave_vnc_caracter_fuera_latin1_lanza_valueerror(self):
        """A5: clave_vnc("ñ€") lanza ValueError (€ no cabe en latin-1)"""
        with pytest.raises(ValueError):
            clave_vnc("ñ€")


class TestRespuestaDesafio:
    """Pruebas A6-A7: respuesta_desafio"""

    def test_A6_respuesta_desafio_password(self):
        """A6: respuesta_desafio("password", bytes(range(16))) = b8 66 92 41 25 c8 ee bb 9d eb c1 db 61 c5 38 e2"""
        desafio = bytes(range(16))
        resultado = respuesta_desafio("password", desafio)
        esperado = bytes([
            0xb8, 0x66, 0x92, 0x41, 0x25, 0xc8, 0xee, 0xbb,
            0x9d, 0xeb, 0xc1, 0xdb, 0x61, 0xc5, 0x38, 0xe2
        ])
        assert resultado == esperado

    def test_A7_respuesta_desafio_longitud_invalida_lanza_valueerror(self):
        """A7: respuesta_desafio("password", bytes(15)) lanza ValueError"""
        with pytest.raises(ValueError):
            respuesta_desafio("password", bytes(15))


class TestKeysymDeCaracter:
    """Pruebas A8-A12: keysym_de_caracter"""

    def test_A8_keysym_ascii_basicos(self):
        """A8: keysym_de_caracter("a")/"A"/" "/"#" = 0x61/0x41/0x20/0x23"""
        assert keysym_de_caracter("a") == 0x61
        assert keysym_de_caracter("A") == 0x41
        assert keysym_de_caracter(" ") == 0x20
        assert keysym_de_caracter("#") == 0x23

    def test_A9_keysym_latin1_con_tilde(self):
        """A9: keysym_de_caracter("á")/"é"/"í"/"ó"/"ú"/"ü" = 0xE1/0xE9/0xED/0xF3/0xFA/0xFC"""
        assert keysym_de_caracter("á") == 0xE1
        assert keysym_de_caracter("é") == 0xE9
        assert keysym_de_caracter("í") == 0xED
        assert keysym_de_caracter("ó") == 0xF3
        assert keysym_de_caracter("ú") == 0xFA
        assert keysym_de_caracter("ü") == 0xFC

    def test_A10_keysym_latin1_especial(self):
        """A10: keysym_de_caracter("ñ")/"Ñ"/"¿"/"¡" = 0xF1/0xD1/0xBF/0xA1"""
        assert keysym_de_caracter("ñ") == 0xF1
        assert keysym_de_caracter("Ñ") == 0xD1
        assert keysym_de_caracter("¿") == 0xBF
        assert keysym_de_caracter("¡") == 0xA1

    def test_A11_keysym_fuera_latin1(self):
        """A11: keysym_de_caracter("€") = 0x010020AC"""
        assert keysym_de_caracter("€") == 0x010020AC

    def test_A12_keysym_invalidos_lanzan_valueerror(self):
        """A12: keysym_de_caracter(""), ("ab"), ("\n"), ("\t") lanzan ValueError"""
        with pytest.raises(ValueError):
            keysym_de_caracter("")
        with pytest.raises(ValueError):
            keysym_de_caracter("ab")
        with pytest.raises(ValueError):
            keysym_de_caracter("\n")
        with pytest.raises(ValueError):
            keysym_de_caracter("\t")


class TestKeysymDeTecla:
    """Pruebas A13-A15: keysym_de_tecla"""

    def test_A13_keysym_enter_variantes(self):
        """A13: keysym_de_tecla("Enter")/("enter")/("Return") = 0xFF0D"""
        assert keysym_de_tecla("Enter") == 0xFF0D
        assert keysym_de_tecla("enter") == 0xFF0D
        assert keysym_de_tecla("Return") == 0xFF0D

    def test_A14_keysym_tab_esc(self):
        """A14: keysym_de_tecla("Tab")/("Esc")/("Escape") = 0xFF09/0xFF1B/0xFF1B"""
        assert keysym_de_tecla("Tab") == 0xFF09
        assert keysym_de_tecla("Esc") == 0xFF1B
        assert keysym_de_tecla("Escape") == 0xFF1B

    def test_A15_keysym_invalidos_lanzan_valueerror(self):
        """A15: keysym_de_tecla("F13"), ("") lanzan ValueError"""
        with pytest.raises(ValueError):
            keysym_de_tecla("F13")
        with pytest.raises(ValueError):
            keysym_de_tecla("")


class TestMsgPointer:
    """Pruebas A16-A17: msg_pointer"""

    def test_A16_msg_pointer_normal(self):
        """A16: msg_pointer(1, 640, 400) = 05 01 02 80 01 90"""
        resultado = msg_pointer(1, 640, 400)
        assert resultado == bytes([0x05, 0x01, 0x02, 0x80, 0x01, 0x90])

    def test_A17_msg_pointer_cero(self):
        """A17: msg_pointer(0, 0, 0) = 05 00 00 00 00 00"""
        resultado = msg_pointer(0, 0, 0)
        assert resultado == bytes([0x05, 0x00, 0x00, 0x00, 0x00, 0x00])


class TestMsgKey:
    """Pruebas A18-A19: msg_key"""

    def test_A18_msg_key_down(self):
        """A18: msg_key(True, 0x61) = 04 01 00 00 00 00 00 61"""
        resultado = msg_key(True, 0x61)
        assert resultado == bytes([0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x61])

    def test_A19_msg_key_up(self):
        """A19: msg_key(False, 0xFF0D) = 04 00 00 00 00 00 FF 0D"""
        resultado = msg_key(False, 0xFF0D)
        assert resultado == bytes([0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x0D])


class TestMsgSetPixelFormat:
    """Prueba A20: msg_set_pixel_format"""

    def test_A20_msg_set_pixel_format(self):
        """A20: msg_set_pixel_format() = bytes esperados"""
        resultado = msg_set_pixel_format()
        # 00 00 00 00 + 20 18 00 01 00 FF 00 FF 00 FF 10 08 00 00 00 00
        esperado = (
            b"\x00\x00\x00\x00" +
            b"\x20\x18\x00\x01\x00\xFF\x00\xFF\x00\xFF\x10\x08\x00\x00\x00\x00"
        )
        assert resultado == esperado


class TestMsgSetEncodings:
    """Prueba A21: msg_set_encodings"""

    def test_A21_msg_set_encodings(self):
        """A21: msg_set_encodings() = 02 00 00 01 00 00 00 00 (solo Raw)"""
        resultado = msg_set_encodings()
        assert resultado == bytes([0x02, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])


class TestMsgUpdateRequest:
    """Pruebas A22-A23: msg_update_request"""

    def test_A22_msg_update_request_no_incremental(self):
        """A22: msg_update_request(False, 0, 0, 1280, 800) = 03 00 00 00 00 00 05 00 03 20"""
        resultado = msg_update_request(False, 0, 0, 1280, 800)
        assert resultado == bytes([0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, 0x00, 0x03, 0x20])

    def test_A23_msg_update_request_incremental(self):
        """A23: msg_update_request(True, 10, 20, 30, 40) = 03 01 00 0A 00 14 00 1E 00 28"""
        resultado = msg_update_request(True, 10, 20, 30, 40)
        assert resultado == bytes([0x03, 0x01, 0x00, 0x0A, 0x00, 0x14, 0x00, 0x1E, 0x00, 0x28])


def _decodificar_png_rgb(png: bytes):
    """NOTA: decodificador de PNG mínimo para pruebas (sin Pillow):
    verifica firma, chunks con CRC, IHDR RGB de 8 bits, IDAT con zlib y
    filtro 0. Devuelve (ancho, alto, profundidad, tipo_color, pixeles RGB)."""
    import struct
    import zlib

    firma = b"\x89PNG\r\n\x1a\n"
    assert png[:8] == firma, "firma PNG incorrecta"

    chunks = []
    pos = 8
    while pos < len(png):
        assert pos + 12 <= len(png), "chunk truncado"
        (largo,) = struct.unpack("!I", png[pos:pos + 4])
        tipo = png[pos + 4:pos + 8]
        datos = png[pos + 8:pos + 8 + largo]
        assert len(datos) == largo, "chunk truncado"
        (crc,) = struct.unpack("!I", png[pos + 8 + largo:pos + 12 + largo])
        assert crc == zlib.crc32(tipo + datos) & 0xFFFFFFFF, f"CRC inválido en {tipo}"
        chunks.append((tipo, datos))
        pos += 12 + largo

    assert chunks, "PNG sin chunks"
    assert chunks[-1][0] == b"IEND", "falta IEND"

    (ihdr,) = [d for t, d in chunks if t == b"IHDR"]
    ancho, alto, profundidad, tipo_color, compresion, filtro, entrelazado = \
        struct.unpack("!IIBBBBB", ihdr)
    assert compresion == 0, "compresión distinta de 0"
    assert filtro == 0, "método de filtro distinto de 0"
    assert entrelazado == 0, "PNG entrelazado"

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
    return ancho, alto, profundidad, tipo_color, pixeles


class TestPngDesdeBgrx:
    """Pruebas A24-A25: png_desde_bgrx"""

    def test_A24_png_desde_bgrx_valido(self):
        """A24: PNG válido (firma, IHDR 2x1 8 bits RGB, IDAT zlib, filtro 0)
        que decodificado da rojo (255,0,0) y azul (0,0,255)"""
        datos = b"\x00\x00\xff\x00" + b"\xff\x00\x00\x00"
        png = png_desde_bgrx(datos, 2, 1)

        ancho, alto, profundidad, tipo_color, pixeles = _decodificar_png_rgb(png)
        assert (ancho, alto) == (2, 1), "IHDR debe ser 2x1"
        assert profundidad == 8, "profundidad debe ser 8 bits"
        assert tipo_color == 2, "tipo de color debe ser RGB"
        assert pixeles == [(255, 0, 0), (0, 0, 255)]

    def test_A25_png_desde_bgrx_longitud_invalida_lanza_valueerror(self):
        """A25: png_desde_bgrx(b"\x00" * 7, 2, 1) lanza ValueError"""
        with pytest.raises(ValueError):
            png_desde_bgrx(b"\x00" * 7, 2, 1)


class TestFraccionNoNegra:
    """Pruebas A26-A27: fraccion_no_negra"""

    def test_A26_fraccion_no_negra_todo_negro(self):
        """A26: fraccion_no_negra(bytes(400)) = 0.0 (100 píxeles en cero)"""
        resultado = fraccion_no_negra(bytes(400))
        assert resultado == 0.0

    def test_A27_fraccion_no_negra_mitad(self):
        """A27: fraccion_no_negra con mitad blanco = 0.5 (UMBRAL_NEGRO = 16)"""
        # 50 píxeles blancos (0xFF, 0xFF, 0xFF, 0x00) + 50 negros
        datos = b"\xff\xff\xff\x00" * 50 + bytes(200)
        resultado = fraccion_no_negra(datos)
        assert resultado == 0.5

    def test_umbral_negro_constante_existe(self):
        """Verificar que existe la constante UMBRAL_NEGRO"""
        assert UMBRAL_NEGRO == 16


def _png_estructura_valida(png: bytes, ancho_esperado: int, alto_esperado: int) -> None:
    """NOTA: valida la estructura de un PNG (firma, chunks con CRC, IHDR,
    IDAT con zlib) sin decodificar píxel a píxel."""
    import struct
    import zlib

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
    ancho, alto, profundidad, tipo_color, compresion, filtro, entrelazado = \
        struct.unpack("!IIBBBBB", ihdr)
    assert (ancho, alto) == (ancho_esperado, alto_esperado)
    assert (profundidad, tipo_color) == (8, 2), "IHDR debe ser 8 bits RGB"
    assert (compresion, filtro, entrelazado) == (0, 0, 0)
    idat = b"".join(d for t, d in chunks if t == b"IDAT")
    crudo = zlib.decompress(idat)
    assert len(crudo) == alto * (1 + ancho * 3), "IDAT con tamaño inesperado"


class TestRendimiento:
    """Pruebas A28-A29: rendimiento con pantalla completa (prosa 11)."""

    def test_A28_png_desde_bgrx_rapido(self):
        """A28: png_desde_bgrx(os.urandom(1280*800*4), 1280, 800) -> un PNG
        válido en menos de 0.5 s (zlib nivel 1, constante NIVEL_ZLIB)."""
        from frontier_agente.rfb_protocolo import NIVEL_ZLIB
        assert NIVEL_ZLIB == 1
        datos = os.urandom(1280 * 800 * 4)
        t0 = time.perf_counter()
        png = png_desde_bgrx(datos, 1280, 800)
        transcurrido = time.perf_counter() - t0
        assert transcurrido < 0.5, f"png_desde_bgrx tardó {transcurrido:.3f} s"
        _png_estructura_valida(png, 1280, 800)

    def test_A29_fraccion_no_negra_rapida(self):
        """A29: fraccion_no_negra(os.urandom(1280*800*4)) -> un número mayor
        que 0.99 en menos de 0.1 s (sin bucle por píxel)."""
        datos = os.urandom(1280 * 800 * 4)
        t0 = time.perf_counter()
        resultado = fraccion_no_negra(datos)
        transcurrido = time.perf_counter() - t0
        assert resultado > 0.99
        assert transcurrido < 0.1, f"fraccion_no_negra tardó {transcurrido:.3f} s"