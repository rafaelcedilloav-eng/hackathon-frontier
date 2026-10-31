"""Pruebas de frontier_agente.texto · tabla T del encargo 004 (una prueba por fila)."""
from frontier_agente.texto import (
    normalizar_clave,
    normalizar_valor,
    solo_digitos,
    valores_iguales,
)


def test_t1_normalizar_valor_quita_y_junta_espacios():
    assert normalizar_valor("  Pereira   Centro ") == "pereira centro"


def test_t2_normalizar_valor_conserva_acentos():
    assert normalizar_valor("ÁÑO") == "áño"


def test_t3_normalizar_valor_vacio():
    assert normalizar_valor("") == ""


def test_t4_normalizar_clave_quita_acentos_y_dos_puntos():
    assert normalizar_clave("Teléfono:") == "telefono"


def test_t5_normalizar_clave_guion_bajo_como_espacio():
    assert normalizar_clave("  Razón_Social ") == "razon social"


def test_t6_solo_digitos_ignora_separadores():
    assert solo_digitos("(315) 765-4321") == "3157654321"


def test_t7_valores_iguales_digitos_con_puntos():
    assert valores_iguales("901234567", "901.234.567") is True


def test_t8_valores_iguales_digitos_con_espacios():
    assert valores_iguales("3157654321", "315 765 4321") is True


def test_t9_valores_iguales_digitos_distintos():
    assert valores_iguales("3157654321", "3157654322") is False


def test_t10_valores_iguales_ignora_mayusculas_y_bordes():
    assert valores_iguales("Pereira", "pereira ") is True


def test_t11_valores_iguales_textos_distintos():
    assert valores_iguales("Pereira", "Perera") is False


def test_t12_valores_iguales_direccion_solo_mayusculas():
    assert valores_iguales("Calle 80 # 24-15", "calle 80 # 24-15") is True


def test_t13_valores_iguales_direccion_distinta_compara_texto():
    # Tiene letras: se compara el texto, no los dígitos.
    assert valores_iguales("Calle 80 # 24-15", "Calle 80 # 24-16") is False


def test_t14_valores_iguales_cadenas_vacias():
    assert valores_iguales("", "") is True
    assert valores_iguales("", "x") is False


def test_t15_valores_iguales_acentos_cuentan():
    assert valores_iguales("Café", "Cafe") is False
