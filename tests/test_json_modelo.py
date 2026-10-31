"""
Pruebas para `extraer_json` (Tabla J) de `frontier_agente/json_modelo.py`.
Una prueba por fila de la tabla J.
"""
import pytest

from frontier_agente.json_modelo import extraer_json
from frontier_agente.tipos_agente import ErrorModelo


class TestExtraerJson:
    """Tabla J: extraer_json(texto: str) -> dict; lanza ErrorModelo si no hay un objeto JSON válido."""

    def test_J1_objeto_simple(self):
        # J1: '{"a": 1}' -> {"a": 1}
        assert extraer_json('{"a": 1}') == {"a": 1}

    def test_J2_dentro_de_bloque_de_codigo(self):
        # J2: '```json\n{"a": 1}\n```' -> {"a": 1}
        assert extraer_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_J3_con_texto_alrededor(self):
        # J3: 'Claro: {"x": 5, "y": 7} listo' -> {"x": 5, "y": 7}
        assert extraer_json('Claro: {"x": 5, "y": 7} listo') == {"x": 5, "y": 7}

    def test_J4_objeto_anidado(self):
        # J4: '{"a": {"b": 2}}' -> {"a": {"b": 2}}
        assert extraer_json('{"a": {"b": 2}}') == {"a": {"b": 2}}

    def test_J5_llave_dentro_de_una_cadena(self):
        # J5: '{"t": "una } llave dentro"}' -> {"t": "una } llave dentro"}
        assert extraer_json('{"t": "una } llave dentro"}') == {"t": "una } llave dentro"}

    def test_J6_texto_vacio(self):
        # J6: '' -> ErrorModelo
        with pytest.raises(ErrorModelo):
            extraer_json("")

    def test_J7_sin_json(self):
        # J7: 'sin json' -> ErrorModelo
        with pytest.raises(ErrorModelo):
            extraer_json("sin json")

    def test_J8_lista_no_es_objeto(self):
        # J8: '[1, 2]' -> ErrorModelo (debe ser un objeto)
        with pytest.raises(ErrorModelo):
            extraer_json("[1, 2]")

    def test_J9_json_incompleto(self):
        # J9: '{"a":' -> ErrorModelo
        with pytest.raises(ErrorModelo):
            extraer_json('{"a":')

    def test_J10_dos_objetos_toma_el_primero(self):
        # J10: '{"a": 1} y luego {"b": 2}' -> {"a": 1} (el primero)
        assert extraer_json('{"a": 1} y luego {"b": 2}') == {"a": 1}

    def test_J11_numero_enorme(self):
        # J11: un entero de 5000 dígitos -> ErrorModelo (nunca ValueError).
        with pytest.raises(ErrorModelo):
            extraer_json('{"a": ' + "1" * 5000 + "}")

    def test_J12_anidacion_extrema(self):
        # J12: 100000 corchetes abiertos -> ErrorModelo (nunca RecursionError).
        with pytest.raises(ErrorModelo):
            extraer_json('{"a": ' + "[" * 100000 + "}")
