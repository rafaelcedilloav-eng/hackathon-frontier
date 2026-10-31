"""Pruebas de los objetivos (tabla O): funciones puras de texto, sin modelo ni pantalla.

Cada fila de la tabla O es una prueba con el resultado exacto que dice la
tabla. Los textos esperados van literales.
"""
from frontier_agente.objetivos import objetivo_escribir, objetivo_resolver, objetivo_verificar
from frontier_agente.tipos_agente import Intencion

# NOTA: la intención de crear de la tabla P, con la que corren OB1, OB2 y OB4.
INTENCION_CREAR = Intencion(
    tipo="crear",
    entidad="cliente",
    campos={"nombre": "Tienda Sol", "nit": "901234567"},
    identificador={"nit": "901234567"},
)
INTENCION_MODIFICAR = Intencion(
    tipo="modificar",
    entidad="cliente",
    identificador={"nombre": "Casa Norte"},
    campos={"direccion": "Calle 80 # 24-15"},
)


def test_OB1_objetivo_resolver_busca_y_pide_leer():
    texto = objetivo_resolver(INTENCION_CREAR)
    for trozo in (
        "nit",
        "901234567",
        "cliente",
        "leer",
        "candidatos",
        "no crees, modifiques ni guardes nada",
    ):
        assert trozo in texto, f"falta {trozo!r} en el objetivo de resolver"


def test_OB2_objetivo_escribir_crear_lista_los_campos():
    texto = objetivo_escribir(INTENCION_CREAR, "crear")
    for trozo in ("nombre", "Tienda Sol", "nit", "901234567", "una sola vez"):
        assert trozo in texto, f"falta {trozo!r} en el objetivo de crear"


def test_OB3_objetivo_escribir_modificar_nombra_lo_que_cambia():
    texto = objetivo_escribir(INTENCION_MODIFICAR, "modificar")
    for trozo in ("Casa Norte", "direccion", "Calle 80 # 24-15", "una sola vez"):
        assert trozo in texto, f"falta {trozo!r} en el objetivo de modificar"


def test_OB4_objetivo_verificar_pide_leer_sin_los_valores():
    texto = objetivo_verificar(INTENCION_CREAR)
    for trozo in ("leer", "nombre", "nit"):
        assert trozo in texto, f"falta {trozo!r} en el objetivo de verificar"
    # NOTA: el identificador se menciona una sola vez y el valor de nombre ni una.
    assert texto.count("901234567") == 1
    assert "Tienda Sol" not in texto


def test_OB5_ningun_objetivo_nombra_a_la_app_de_practica():
    textos = (
        objetivo_resolver(INTENCION_CREAR),
        objetivo_escribir(INTENCION_CREAR, "crear"),
        objetivo_escribir(INTENCION_MODIFICAR, "modificar"),
        objetivo_verificar(INTENCION_CREAR),
    )
    for texto in textos:
        for prohibido in ("SIGECOM", "Clientes", "Maestros", "Comercial"):
            assert prohibido not in texto, f"el objetivo nombra {prohibido!r}"


def test_OB6_objetivo_de_crear_explica_las_listas_desplegables():
    texto = objetivo_escribir(INTENCION_CREAR, "crear")
    for trozo in ("elegir_opcion", "Tab", "una sola vez"):
        assert trozo in texto, f"falta {trozo!r} en el objetivo de crear"
    # NOTA: la fila pide que explique cómo se llena una lista desplegable:
    # con un clic en la opción, declarando funcion elegir_opcion y texto con el valor.
    for trozo in ("desplegable", "clic", "funcion", "texto"):
        assert trozo in texto, f"falta {trozo!r} en la explicación de la lista desplegable"