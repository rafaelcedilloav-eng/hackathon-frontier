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


# --------------------------------------------- Bloque 7 (tabla O3 del encargo 009)
# NOTA: las funciones de este bloque aún no existen: se importan dentro de
# cada prueba para que OB1-OB6 sigan corriendo y solo fallen las nuevas.


def test_OB7_objetivo_responder_habla_de_hoy_total_y_respuesta():
    from frontier_agente.objetivos import objetivo_responder

    intencion = Intencion(
        tipo="consultar",
        pregunta="¿Cuántas facturas vencidas tiene Ferretería Ruiz?",
        identificador={"nombre": "Ferretería Ruiz"},
        filtros={"estado": "vencida"},
    )
    texto = objetivo_responder(intencion)
    # NOTA: «hoy» se comprueba sin distinguir mayúsculas (la fila lo escribe
    # en minúscula; el objetivo puede decir «hoy» o «Hoy» de la app).
    assert "hoy" in texto.lower(), "falta 'hoy' en el objetivo de responder"
    for trozo in ("total", "respuesta", "Ferretería Ruiz", "vencida"):
        assert trozo in texto, f"falta {trozo!r} en el objetivo de responder"
    # NOTA: la fila pide que no esté «guardar» como orden: la palabra no aparece
    # (una prohibición como «no guardes nada» sí pasaría, es otra palabra).
    assert "guardar" not in texto.lower(), "el objetivo de responder ordena guardar"


def test_OB8_objetivo_responder_explica_el_formato_de_dos_datos():
    from frontier_agente.objetivos import objetivo_responder

    intencion = Intencion(
        tipo="consultar",
        pregunta="¿Cuántas citas hay el lunes y cuántas el martes?",
    )
    texto = objetivo_responder(intencion)
    # NOTA: la fila pide «; » (el formato de dos datos: «dato 1; dato 2»).
    assert "; " in texto, "falta el formato de dos datos en el objetivo de responder"
    assert "respuesta" in texto


def test_OB9_objetivo_exportar_filtra_y_pulsa_una_sola_vez():
    from frontier_agente.objetivos import objetivo_exportar

    intencion = Intencion(tipo="exportar", filtros={"desde": "septiembre"})
    texto = objetivo_exportar(intencion)
    for trozo in ("septiembre", "Hoy", "exportar", "una sola vez"):
        assert trozo in texto, f"falta {trozo!r} en el objetivo de exportar"


# --------------------------------------------- Bloque 8 (tabla OB4 del encargo 010)
# NOTA: AVISO_EN_OBJETIVO aún no existe: se importa dentro de cada prueba
# nueva para que OB1-OB9 sigan corriendo y solo fallen las nuevas.


def test_OB10_todos_los_objetivos_terminan_con_el_aviso():
    # OB10: cada una de las cinco funciones (objetivo_resolver,
    # objetivo_escribir —crear y modificar—, objetivo_verificar,
    # objetivo_responder, objetivo_exportar) termina con la frase fija
    # AVISO_EN_OBJETIVO (constante única en objetivos.py).
    from frontier_agente.objetivos import (
        AVISO_EN_OBJETIVO,
        objetivo_exportar,
        objetivo_responder,
    )

    assert AVISO_EN_OBJETIVO == (
        "Si un aviso, modal o ventana emergente tapa la app, ciérralo primero "
        "con la función cerrar_aviso (no es parte de la tarea)."
    )
    intencion_consultar = Intencion(
        tipo="consultar",
        pregunta="¿Cuántos registros hay con filtro activo?",
        filtros={"estado": "activo"},
    )
    intencion_exportar = Intencion(tipo="exportar", filtros={"desde": "septiembre"})
    objetivos = (
        objetivo_resolver(INTENCION_CREAR),
        objetivo_escribir(INTENCION_CREAR, "crear"),
        objetivo_escribir(INTENCION_MODIFICAR, "modificar"),
        objetivo_verificar(INTENCION_CREAR),
        objetivo_responder(intencion_consultar),
        objetivo_exportar(intencion_exportar),
    )
    for texto in objetivos:
        assert texto.rstrip().endswith(AVISO_EN_OBJETIVO), texto[-80:]


def test_OB11_objetivo_verificar_habla_del_significado():
    # OB11: objetivo_verificar dice que cada campo se lee por su significado,
    # aunque la etiqueta de la pantalla se llame distinto (palabra "significado").
    texto = objetivo_verificar(INTENCION_CREAR)
    assert "significado" in texto