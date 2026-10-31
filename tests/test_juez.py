"""Pruebas de frontier_agente.juez · tabla J del encargo 004 (una prueba por fila)."""
from frontier_agente.juez import comparar_campos
from frontier_agente.tipos_agente import Diferencia


def test_j1_coincide_con_separadores_y_mayusculas():
    assert comparar_campos(
        {"nit": "901234567", "ciudad": "Cali"},
        {"nit": "901.234.567", "ciudad": "cali"},
    ) == []


def test_j2_acento_es_diferencia():
    assert comparar_campos({"ciudad": "Cali"}, {"ciudad": "Calí"}) == [
        Diferencia("ciudad", "Cali", "Calí")
    ]


def test_j3_campo_faltante():
    assert comparar_campos({"a": "1", "b": "2"}, {"a": "1"}) == [
        Diferencia("b", "2", "")
    ]


def test_j4_campo_nulo():
    assert comparar_campos({"a": "1"}, {"a": None}) == [
        Diferencia("a", "1", "")
    ]


def test_j5_llaves_extra_se_ignoran():
    assert comparar_campos({"a": "1"}, {"a": "1", "z": "extra"}) == []


def test_j6_nada_esperado():
    assert comparar_campos({}, {"a": "1"}) == []


def test_j7_dos_diferencias_en_orden():
    assert comparar_campos({"a": "x", "b": "y"}, {"a": "q", "b": "r"}) == [
        Diferencia("a", "x", "q"),
        Diferencia("b", "y", "r"),
    ]


def test_j8_lectura_no_dict_o_vacia():
    # Una lectura que no es un dict o viene vacía nunca da [] si había algo esperado.
    assert comparar_campos({"a": "1", "b": "2"}, None) == [
        Diferencia("a", "1", ""),
        Diferencia("b", "2", ""),
    ]
    assert comparar_campos({"a": "1"}, "texto") == [Diferencia("a", "1", "")]
    assert comparar_campos({"a": "1"}, {}) == [Diferencia("a", "1", "")]
