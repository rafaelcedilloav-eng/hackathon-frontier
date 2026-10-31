"""Pruebas del intérprete (tabla I): interpretar la tarea con un llamar de mentira.

Cada fila de la tabla I es una prueba con el resultado exacto que dice la
tabla. La validación de la intención y la extracción del JSON son las de
verdad; lo falso es solo el modelo.
"""
import asyncio

import pytest

from falsos_agente import LlamarGuionado
from frontier_agente.interprete import interpretar
from frontier_agente.tipos_agente import ErrorModelo, Intencion

TAREA = "Registra al cliente Tienda Sol, NIT 901234567."
JSON_CREAR = (
    '{"tipo":"crear","entidad":"cliente","identificador":{"nit":"901234567"},'
    '"campos":{"nombre":"Tienda Sol","nit":"901234567"}}'
)


def test_IN1_json_plano_da_la_intencion_valida():
    llamar = LlamarGuionado(JSON_CREAR)
    intencion = asyncio.run(interpretar(TAREA, llamar))
    assert intencion == Intencion(
        tipo="crear",
        entidad="cliente",
        identificador={"nit": "901234567"},
        campos={"nombre": "Tienda Sol", "nit": "901234567"},
    )
    assert len(llamar.llamadas) == 1
    mensajes, imagen = llamar.llamadas[0]
    assert imagen is None
    assert any(
        m.get("role") == "system" and "JSON" in m.get("content", "") for m in mensajes
    )


def test_IN2_json_envuelto_en_bloque_de_codigo_da_igual():
    envuelta = f"```json\n{JSON_CREAR}\n```"
    llamar = LlamarGuionado(envuelta)
    intencion = asyncio.run(interpretar(TAREA, llamar))
    assert intencion == Intencion(
        tipo="crear",
        entidad="cliente",
        identificador={"nit": "901234567"},
        campos={"nombre": "Tienda Sol", "nit": "901234567"},
    )


def test_IN3_valor_ajeno_a_la_tarea_queda_en_campos_exentos():
    respuesta = (
        '{"tipo":"crear","entidad":"cliente","identificador":{"nit":"901234567"},'
        '"campos":{"nombre":"Tienda Sol","nit":"901234567","ciudad":"Medellín"}}'
    )
    llamar = LlamarGuionado(respuesta)
    intencion = asyncio.run(interpretar(TAREA, llamar))
    # NOTA: regla nueva del bloque 5: un valor de campos fuera de la tarea pasa a exento, no a motivo_fallo.
    assert intencion.motivo_fallo == ""
    assert "ciudad" in intencion.campos_exentos


def test_IN4_error_de_modelo_al_llamar_sale_tal_cual():
    llamar = LlamarGuionado(ErrorModelo("sin servicio"))
    with pytest.raises(ErrorModelo):
        asyncio.run(interpretar(TAREA, llamar))


def test_IN5_respuesta_que_no_es_json_lanza_error_de_modelo():
    llamar = LlamarGuionado("lo siento")
    with pytest.raises(ErrorModelo):
        asyncio.run(interpretar(TAREA, llamar))


def test_IN6_tarea_destructiva_marca_peligrosa():
    llamar = LlamarGuionado('{"tipo":"otro"}')
    intencion = asyncio.run(interpretar("Borra todos los pedidos", llamar))
    assert intencion.peligrosa is True