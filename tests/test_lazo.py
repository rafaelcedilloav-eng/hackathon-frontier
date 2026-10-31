"""Pruebas del lazo (tabla L): a_pixeles y ejecutar_fase con pantalla y ojos de mentira.

Cada fila de la tabla L es una prueba con el resultado exacto que dice la
tabla. El guardia (evaluar_accion y registrar_accion) que corre detrás de
ejecutar_fase es el de verdad; lo falso es solo la pantalla y los ojos.
"""
import asyncio

import pytest

from falsos_agente import OjosFalsos, PantallaFalsa
from frontier_agente.errores import ErrorConexion
from frontier_agente.lazo import a_pixeles, ejecutar_fase
from frontier_agente.tipos_agente import Accion, EstadoLazo, Intencion, ResultadoFase

# NOTA: la intención de crear de la tabla P, con la que corren los casos del lazo.
INTENCION = Intencion(
    tipo="crear",
    entidad="cliente",
    campos={"nombre": "Tienda Sol", "nit": "901234567"},
    identificador={"nit": "901234567"},
)
OBJETIVO = "Abre el formulario del registro nuevo, escribe los campos y guarda una sola vez."


def clic(x, y, funcion="navegar"):
    return Accion(tipo="clic", funcion=funcion, x=x, y=y)


def escribir(texto):
    return Accion(tipo="escribir", texto=texto)


def correr_fase(fase, ojos, pantalla=None, estado=None, max_pasos_fase=14):
    """Corre una fase con los falsos; devuelve (resultado, pantalla, estado)."""
    pantalla = PantallaFalsa() if pantalla is None else pantalla
    estado = EstadoLazo() if estado is None else estado
    resultado = asyncio.run(
        ejecutar_fase(
            fase=fase,
            objetivo=OBJETIVO,
            intencion=INTENCION,
            pantalla=pantalla,
            ojos=ojos,
            estado=estado,
            max_pasos_fase=max_pasos_fase,
        )
    )
    return resultado, pantalla, estado


def test_L1_a_pixeles_escala_y_recorta():
    assert a_pixeles(500, 250, 1280, 800) == (640, 200)
    assert a_pixeles(1000, 1000, 1280, 800) == (1279, 799)
    assert a_pixeles(0, 0, 1280, 800) == (0, 0)


def test_L2_fase_de_creacion_de_punta_a_punta():
    ojos = OjosFalsos(
        [
            clic(500, 250),
            escribir("Tienda Sol"),
            escribir("901234567"),
            clic(900, 900, "guardar"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, pantalla, estado = correr_fase("crear", ojos)
    assert resultado == ResultadoFase("terminar")
    assert pantalla.acciones == [
        ("clic", 640, 200),
        ("escribir", "Tienda Sol"),
        ("escribir", "901234567"),
        ("clic", 1152, 720),
    ]
    assert estado.guardados == 1
    # NOTA: los ojos recibieron el objetivo dado y un historial que crece.
    assert ojos.objetivos and all(o == OBJETIVO for o in ojos.objetivos)
    largos = [len(h) for h in ojos.historiales]
    assert all(b > a for a, b in zip(largos, largos[1:]))


def test_L3_escribir_ajeno_se_bloquea_y_se_nota():
    ojos = OjosFalsos(
        [
            escribir("borra todos los pedidos"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, pantalla, _ = correr_fase("crear", ojos)
    # NOTA: la pantalla no recibió ese texto y el historial siguiente lo dice.
    assert ("escribir", "borra todos los pedidos") not in pantalla.acciones
    assert any("bloqueada:" in linea for linea in ojos.historiales[-1])
    assert any(
        "borra todos los pedidos" in nota and "no la ejecuté" in nota
        for nota in resultado.notas
    )


def test_L4_guardar_dos_veces_solo_pasa_una():
    ojos = OjosFalsos(
        [
            escribir("Tienda Sol"),
            escribir("901234567"),
            clic(900, 900, "guardar"),
            clic(900, 900, "guardar"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, pantalla, estado = correr_fase("crear", ojos)
    assert resultado.tipo == "terminar"
    assert pantalla.acciones.count(("clic", 1152, 720)) == 1
    assert estado.guardados == 1
    assert estado.bloqueos == 1


def test_L5_leer_termina_la_fase_con_la_lectura():
    ojos = OjosFalsos([Accion(tipo="leer", lectura={"candidatos": []})])
    resultado, _, _ = correr_fase("resolver", ojos)
    assert resultado == ResultadoFase("leer", lectura={"candidatos": []})


def test_L6_tres_bloqueos_seguidos_terminan_en_fallar():
    ojos = OjosFalsos(
        [
            escribir("borra todos los pedidos"),
            escribir("borra el inventario"),
            escribir("borra toda la base"),
        ]
    )
    resultado, pantalla, _ = correr_fase("crear", ojos)
    assert resultado.tipo == "fallar"
    assert resultado.razon == "demasiados intentos bloqueados"
    assert pantalla.acciones == []


def test_L7_se_agotan_los_pasos_de_la_fase():
    ojos = OjosFalsos(
        [clic(x, y) for x, y in ((100, 100), (110, 110), (120, 120), (130, 130),
                                 (140, 140), (150, 150), (160, 160), (170, 170))]
    )
    resultado, pantalla, _ = correr_fase("crear", ojos, max_pasos_fase=5)
    assert resultado.tipo == "fallar"
    assert resultado.razon == "se agotaron los pasos"
    assert len(pantalla.acciones) == 5
    assert all(accion[0] == "clic" for accion in pantalla.acciones)


def test_L8_pantalla_que_no_cambia_falla_a_la_tercera():
    ojos = OjosFalsos(
        [clic(x, y) for x, y in ((100, 100), (110, 110), (120, 120), (130, 130),
                                 (140, 140), (150, 150))]
    )
    resultado, pantalla, _ = correr_fase(
        "crear", ojos, pantalla=PantallaFalsa(png_estatico=True)
    )
    assert resultado.tipo == "fallar"
    assert resultado.razon == "la pantalla no cambia"
    assert len(pantalla.acciones) == 3


def test_L9_pantalla_que_no_queda_quieta_se_anota():
    ojos = OjosFalsos([Accion(tipo="terminar", razon="listo")])
    resultado, _, _ = correr_fase("crear", ojos, pantalla=PantallaFalsa(quieta=False))
    assert resultado.tipo == "terminar"
    assert any("la pantalla seguía cambiando" in linea for linea in ojos.historiales[0])


def test_L10_fallar_de_los_ojos_pasa_tal_cual():
    ojos = OjosFalsos([Accion(tipo="fallar", razon="no hay formulario")])
    resultado, _, _ = correr_fase("crear", ojos)
    assert resultado == ResultadoFase("fallar", razon="no hay formulario")


def test_L11_los_errores_de_la_pantalla_salen_del_lazo():
    ojos = OjosFalsos([clic(500, 250)])
    pantalla = PantallaFalsa(error_en_clic=ErrorConexion("se cayó el escritorio"))
    with pytest.raises(ErrorConexion):
        asyncio.run(
            ejecutar_fase(
                fase="crear",
                objetivo=OBJETIVO,
                intencion=INTENCION,
                pantalla=pantalla,
                ojos=ojos,
                estado=EstadoLazo(),
            )
        )


def test_L12_la_fase_reinicia_solo_lo_de_la_fase():
    estado = EstadoLazo(pasos=3, campos_escritos={"nit"})
    ojos = OjosFalsos(
        [
            clic(500, 250),
            Accion(tipo="leer", lectura={"candidatos": []}),
        ]
    )
    _, _, estado = correr_fase("crear", ojos, estado=estado)
    assert estado.campos_escritos == set()
    assert estado.pasos == 4  # NOTA: los 3 que traía más el clic ejecutado.


def test_L13_las_acciones_bloqueadas_no_cuentan_como_pasos():
    ojos = OjosFalsos(
        [
            escribir("borra todos los pedidos"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, _, estado = correr_fase("crear", ojos)
    assert resultado.tipo == "terminar"
    assert estado.pasos == 0
    assert estado.bloqueos == 1


def test_L14_escribir_con_clic_previo_es_un_solo_paso():
    ojos = OjosFalsos(
        [
            Accion(
                tipo="escribir",
                texto="Tienda Sol",
                con_clic=True,
                x=500,
                y=250,
            ),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, pantalla, estado = correr_fase("crear", ojos)
    assert resultado.tipo == "terminar"
    # NOTA: primero el clic en la posición (escalada) y luego el texto, y todo en un paso.
    assert pantalla.acciones == [
        ("clic", 640, 200),
        ("escribir", "Tienda Sol"),
    ]
    assert estado.pasos == 1