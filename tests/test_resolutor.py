"""Pruebas de frontier_agente.resolutor · tabla V del encargo 004 (una prueba por fila)."""
from frontier_agente.resolutor import resolver
from frontier_agente.tipos_agente import Candidato

A = Candidato("52345678", {"nombre": "Ana Torres", "ciudad": "Bogotá"})
B = Candidato("1019876543", {"nombre": "Ana Torres", "ciudad": "Medellín"})


def test_v1_sin_candidatos():
    r = resolver([], {"nombre": "Ana Torres"})
    assert r.tipo == "ninguno"


def test_v2_un_candidato():
    r = resolver([A], {"nombre": "Ana Torres"})
    assert r.tipo == "uno"
    assert r.elegido == A


def test_v3_dos_iguales_son_ambiguos():
    r = resolver([A, B], {"nombre": "Ana Torres"})
    assert r.tipo == "ambiguo"
    assert r.candidatos == (A, B)
    assert r.elegido is None


def test_v4_la_ciudad_distingue():
    r = resolver([A, B], {"nombre": "Ana Torres", "ciudad": "Medellín"})
    assert r.tipo == "uno"
    assert r.elegido == B


def test_v5_ciudad_que_no_coincide_no_descarta():
    r = resolver([A, B], {"nombre": "Ana Torres", "ciudad": "Cali"})
    assert r.tipo == "ambiguo"
    assert r.candidatos == (A, B)


def test_v6_paso_a_por_identificador():
    r = resolver([A, B], {"documento": "1019876543"})
    assert r.tipo == "uno"
    assert r.elegido == B


def test_v7_llave_y_valor_normalizados():
    r = resolver([A, B], {"Ciudad": "bogotá"})
    assert r.tipo == "uno"
    assert r.elegido == A


def test_v8_llave_inexistente_no_distingue():
    r = resolver([A, B], {"sucursal": "Norte"})
    assert r.tipo == "ambiguo"


def test_v9_candidato_repetido_cuenta_como_uno():
    r = resolver([A, A], {"nombre": "Ana Torres"})
    assert r.tipo == "uno"
    assert r.elegido == A
