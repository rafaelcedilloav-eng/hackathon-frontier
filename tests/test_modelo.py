"""
Pruebas para `frontier_agente/modelo.py` (Tabla M).
Una prueba por fila de la tabla M, más una prueba de constantes (borde: la
especificación fija sus valores exactos en la prosa). Los `enviar` falsos se
definen aquí mismo. Sin pytest-asyncio: se usa asyncio.run(...).
"""
import asyncio
import json
from pathlib import Path

import pytest

from frontier_agente.errores import ErrorConfiguracion
from frontier_agente.modelo import (
    MODELO_ATASCO,
    MODELO_OJOS,
    TOPE_LLAMADA_S,
    URL_OPENROUTER,
    VARIABLE_LLAVE,
    construir_cuerpo,
    leer_respuesta,
    llamar_modelo,
)
from frontier_agente.tipos_agente import ErrorModelo, RespuestaModelo

MENSAJES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


class TestConstantes:
    """Borde: la especificación fija el valor exacto de las cinco constantes."""

    def test_constantes_tienen_valor_exacto(self):
        assert MODELO_OJOS == "anthropic/claude-haiku-5.5"
        assert MODELO_ATASCO == "anthropic/claude-sonnet-5.5"
        assert URL_OPENROUTER == "https://openrouter.ai/api/v1/chat/completions"
        assert VARIABLE_LLAVE == "OPENROUTER_API_KEY"
        assert TOPE_LLAMADA_S == 60.0


class TestConstruirCuerpo:
    """Tabla M (M1-M3): construir_cuerpo(mensajes, imagen_png, *, modelo, esfuerzo) -> dict."""

    def test_M1_sin_imagen_cuerpo_exacto(self):
        # M1: sin imagen, el cuerpo es exactamente el esperado y los mensajes quedan igual.
        cuerpo = construir_cuerpo(MENSAJES, None, modelo="m", esfuerzo="low")
        assert cuerpo == {
            "model": "m",
            "messages": [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
            ],
            "temperature": 0,
            "reasoning": {"effort": "low"},
            "usage": {"include": True},
        }

    def test_M2_con_imagen_contenido_en_partes(self):
        # M2: con imagen, el último mensaje user cambia su content por la lista de partes.
        cuerpo = construir_cuerpo(MENSAJES, b"\x89PNGabc", modelo="m", esfuerzo="low")
        assert cuerpo["messages"][0] == {"role": "system", "content": "s"}
        contenido = cuerpo["messages"][1]["content"]
        assert cuerpo["messages"][1]["role"] == "user"
        assert contenido[0] == {"type": "text", "text": "u"}
        # NOTA: base64 de b"\x89PNGabc", escrito literal como pide la fila.
        assert contenido[1] == {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBOR2FiYw=="},
        }

    def test_M3_no_modifica_la_entrada(self):
        # M3: la lista de mensajes de entrada no queda modificada.
        mensajes = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
        ]
        copia = [dict(m) for m in mensajes]
        construir_cuerpo(mensajes, b"\x89PNGabc", modelo="m", esfuerzo="low")
        assert mensajes == copia


class TestLeerRespuesta:
    """Tabla M (M4-M7): leer_respuesta(respuesta: dict) -> RespuestaModelo."""

    def test_M4_contenido_de_texto(self):
        # M4: texto plano con costo -> RespuestaModelo("hola", 0.002)
        respuesta = {"choices": [{"message": {"content": "hola"}}], "usage": {"cost": 0.002}}
        assert leer_respuesta(respuesta) == RespuestaModelo("hola", 0.002)

    def test_M5_contenido_en_partes(self):
        # M5: lista de partes; se juntan las de type == "text"; sin costo -> 0.0
        respuesta = {
            "choices": [
                {"message": {"content": [{"type": "text", "text": "ho"}, {"type": "text", "text": "la"}]}}
            ]
        }
        assert leer_respuesta(respuesta) == RespuestaModelo("hola", 0.0)

    def test_M6_error_del_proveedor_sin_detalles(self):
        # M6: el mensaje del ErrorModelo lleva el código, nunca el cuerpo del proveedor.
        respuesta = {"error": {"message": "detalle-del-proveedor", "code": 402}}
        with pytest.raises(ErrorModelo) as excinfo:
            leer_respuesta(respuesta)
        mensaje = str(excinfo.value)
        assert "402" in mensaje
        assert "detalle-del-proveedor" not in mensaje

    def test_M7_sin_choices(self):
        # M7: {"choices": []} -> ErrorModelo
        with pytest.raises(ErrorModelo):
            leer_respuesta({"choices": []})

    def test_M14_respuestas_malformadas_solo_error_modelo(self):
        # M14: mensaje vacío, choice vacío, choices que no es lista y respuesta vacía;
        # en cada una ErrorModelo, nunca KeyError/TypeError/AttributeError.
        respuestas_malas = (
            {"choices": [{"message": {}}]},
            {"choices": [{}]},
            {"choices": "x"},
            [],
        )
        for respuesta in respuestas_malas:
            with pytest.raises(ErrorModelo):
                leer_respuesta(respuesta)

    def test_M15_costo_ilegible_vale_cero(self):
        # M15: un costo que no es número, o usage null, valen 0.0 sin fallar.
        assert leer_respuesta(
            {"choices": [{"message": {"content": "x"}}], "usage": {"cost": "abc"}}
        ) == RespuestaModelo("x", 0.0)
        assert leer_respuesta(
            {"choices": [{"message": {"content": "x"}}], "usage": None}
        ) == RespuestaModelo("x", 0.0)

    def test_M16_error_no_entero_no_se_muestra(self):
        # M16: si el código del error no es un entero (o error no es dict), nunca se muestra su texto.
        with pytest.raises(ErrorModelo) as excinfo:
            leer_respuesta({"error": {"code": "detalle-secreto"}})
        assert "detalle-secreto" not in str(excinfo.value)
        with pytest.raises(ErrorModelo) as excinfo:
            leer_respuesta({"error": "detalle-secreto"})
        assert "detalle-secreto" not in str(excinfo.value)

    def test_M17_partes_de_texto_invalidas(self):
        # M17: parte sin "text", con text null, con text numérico y lista sin partes de texto
        # -> ErrorModelo en cada una.
        respuestas_malas = (
            {"choices": [{"message": {"content": [{"type": "text"}]}}]},
            {"choices": [{"message": {"content": [{"type": "text", "text": None}]}}]},
            {"choices": [{"message": {"content": [{"type": "text", "text": 5}]}}]},
            {"choices": [{"message": {"content": [{"type": "image_url"}]}}]},
        )
        for respuesta in respuestas_malas:
            with pytest.raises(ErrorModelo):
                leer_respuesta(respuesta)

    def test_M18_costo_enorme_o_no_finito_vale_cero(self):
        # M18: un costo de 400 dígitos, NaN o Infinity (JSON ya cargado) -> 0.0 en los tres.
        respuesta_enorme = json.loads(
            '{"choices":[{"message":{"content":"x"}}],"usage":{"cost": ' + "1" * 400 + "}}"
        )
        assert leer_respuesta(respuesta_enorme) == RespuestaModelo("x", 0.0)
        respuesta_nan = json.loads(
            '{"choices":[{"message":{"content":"x"}}],"usage":{"cost":NaN}}'
        )
        assert leer_respuesta(respuesta_nan) == RespuestaModelo("x", 0.0)
        respuesta_inf = json.loads(
            '{"choices":[{"message":{"content":"x"}}],"usage":{"cost":Infinity}}'
        )
        assert leer_respuesta(respuesta_inf) == RespuestaModelo("x", 0.0)


class TestLlamarModelo:
    """Tabla M (M8-M13): llamar_modelo con `enviar` falso (definido aquí mismo)."""

    def test_M8_enviar_falso_recibe_el_cuerpo(self):
        # M8: el falso devuelve una respuesta válida y recibe el cuerpo con modelo y esfuerzo pedidos.
        recibido = []

        async def enviar_falso(cuerpo, tope_s):
            recibido.append(cuerpo)
            return {"choices": [{"message": {"content": "hola"}}], "usage": {"cost": 0.002}}

        resultado = asyncio.run(
            llamar_modelo(MENSAJES, modelo="m2", esfuerzo="high", enviar=enviar_falso)
        )
        assert resultado == RespuestaModelo("hola", 0.002)
        assert recibido == [
            {
                "model": "m2",
                "messages": [
                    {"role": "system", "content": "s"},
                    {"role": "user", "content": "u"},
                ],
                "temperature": 0,
                "reasoning": {"effort": "high"},
                "usage": {"include": True},
            }
        ]

    def test_M9_excepcion_comun_sin_secretos(self):
        # M9: la excepción de enviar se vuelve ErrorModelo con el nombre de la clase, sin su mensaje.
        async def enviar_falso(cuerpo, tope_s):
            raise TimeoutError("sk-secreto")

        with pytest.raises(ErrorModelo) as excinfo:
            asyncio.run(llamar_modelo(MENSAJES, enviar=enviar_falso))
        mensaje = str(excinfo.value)
        assert "TimeoutError" in mensaje
        assert "sk-secreto" not in mensaje

    def test_M10_excepcion_con_codigo_http(self):
        # M10: si la excepción trae atributo code, el mensaje incluye (HTTP 429).
        class ErrorConCodigo(Exception):
            code = 429

        async def enviar_falso(cuerpo, tope_s):
            raise ErrorConCodigo()

        with pytest.raises(ErrorModelo) as excinfo:
            asyncio.run(llamar_modelo(MENSAJES, enviar=enviar_falso))
        assert "HTTP 429" in str(excinfo.value)

    def test_M11_cancelacion_no_se_convierte(self):
        # M11: asyncio.CancelledError sale tal cual, no se vuelve ErrorModelo.
        async def enviar_falso(cuerpo, tope_s):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(llamar_modelo(MENSAJES, enviar=enviar_falso))

    def test_M12_sin_llave_en_el_entorno(self, monkeypatch):
        # M12: sin OPENROUTER_API_KEY y con el enviar de por defecto -> ErrorConfiguracion.
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(ErrorConfiguracion) as excinfo:
            asyncio.run(llamar_modelo(MENSAJES, enviar=None))
        assert "OPENROUTER_API_KEY" in str(excinfo.value)

    def test_M13_higiene_sin_llave_ni_print(self):
        # M13: modelo.py y ojos.py no contienen "sk-" ni "print(".
        carpeta = Path(__file__).resolve().parents[1] / "frontier_agente"
        for nombre in ("modelo.py", "ojos.py"):
            texto = (carpeta / nombre).read_text(encoding="utf-8")
            assert "sk-" not in texto, f"{nombre} contiene 'sk-'"
            assert "print(" not in texto, f"{nombre} contiene 'print('"
