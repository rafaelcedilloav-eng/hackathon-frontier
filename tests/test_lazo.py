"""Pruebas del lazo (tabla L): a_pixeles y ejecutar_fase con pantalla y ojos de mentira.

Cada fila de la tabla L es una prueba con el resultado exacto que dice la
tabla. El guardia (evaluar_accion y registrar_accion) que corre detrás de
ejecutar_fase es el de verdad; lo falso es solo la pantalla y los ojos.
"""
import asyncio
import json
import time

import pytest

from falsos_agente import OjosFalsos, PantallaFalsa
from falso_rfb import ConfiguracionServidor, Pantalla as PantallaRFB, crear_servidor
from frontier_agente.errores import ErrorConexion
from frontier_agente.lazo import a_pixeles, ejecutar_fase
from frontier_agente.rfb_cliente import ClienteRFB
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


def correr_fase(fase, ojos, pantalla=None, estado=None, max_pasos_fase=14, intencion=INTENCION):
    """Corre una fase con los falsos; devuelve (resultado, pantalla, estado)."""
    pantalla = PantallaFalsa() if pantalla is None else pantalla
    estado = EstadoLazo() if estado is None else estado
    resultado = asyncio.run(
        ejecutar_fase(
            fase=fase,
            objetivo=OBJETIVO,
            intencion=intencion,
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


# --------------------------------------------- Bloque 6 (tabla L2 del encargo 008)


class PantallaFalsaConRueda(PantallaFalsa):
    """PantallaFalsa que además registra la rueda: el desplazar que el lazo
    le manda en píxeles (L2.3)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.desplazamientos = []

    async def desplazar(self, x, y, abajo, veces):
        self.desplazamientos.append(("desplazar", x, y, abajo, veces))


def test_L2_1_bloqueos_seguidos_reinician_con_una_ejecutada():
    # L2.1: bloqueada, permitida (clic navegar), bloqueada, bloqueada, leer
    # -> NO termina por bloqueos (van seguidos: 1, 0, 1, 2); el leer llega.
    ojos = OjosFalsos(
        [
            escribir("borra todos los pedidos"),
            clic(500, 250),
            escribir("borra el inventario"),
            escribir("borra toda la base"),
            Accion(tipo="leer", lectura={"candidatos": []}),
        ]
    )
    resultado, pantalla, estado = correr_fase("crear", ojos)
    assert resultado.tipo == "leer"
    assert resultado.lectura == {"candidatos": []}
    assert estado.bloqueos == 2  # NOTA: el contador quedó en 2, no en 4: se reinicia al ejecutar.
    # NOTA: la permitida del medio sí llegó a la pantalla.
    assert ("clic", 640, 200) in pantalla.acciones


def test_L2_2_tres_bloqueos_seguidos_fallan():
    # L2.2: 3 bloqueadas seguidas -> fallar por "demasiados intentos bloqueados".
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


def test_L2_3_desplazar_llega_a_la_pantalla_en_pixeles():
    # L2.3: desplazar x=500, y=600, abajo, 3; luego leer -> la pantalla recibió
    # desplazar(640, 480, True, 3) (píxeles de 1280×800) y cuenta 1 paso.
    pantalla = PantallaFalsaConRueda()
    ojos = OjosFalsos(
        [
            Accion(tipo="desplazar", x=500, y=600, direccion="abajo", veces=3),
            Accion(tipo="leer", lectura={"candidatos": []}),
        ]
    )
    resultado, pantalla, estado = correr_fase("crear", ojos, pantalla=pantalla)
    assert resultado.tipo == "leer"
    assert pantalla.desplazamientos == [("desplazar", 640, 480, True, 3)]
    assert estado.pasos == 1


# NOTA: la intención de L2.4: relleno a mano el texto_tarea que llena el bloque 5.
INTENCION_CONSULTORIO = Intencion(
    tipo="crear",
    entidad="paciente",
    campos={"habitacion": "302"},
    identificador={"habitacion": "302"},
    texto_tarea="Cámbialo de sitio al consultorio 302.",
)


def test_L2_4_escribir_del_texto_tarea_se_ejecuta_y_no_produce_nota():
    # L2.4: fase crear, ojos piden escribir "Consultorio 302" con
    # texto_tarea="…al consultorio 302…" -> se ejecuta y la nota de inyección
    # no aparece (la nota nunca sale para texto de la tarea).
    ojos = OjosFalsos(
        [
            escribir("Consultorio 302"),
            Accion(tipo="leer", lectura={"candidatos": []}),
        ]
    )
    resultado, pantalla, _ = correr_fase("crear", ojos, intencion=INTENCION_CONSULTORIO)
    assert resultado.tipo == "leer"
    assert ("escribir", "Consultorio 302") in pantalla.acciones
    assert resultado.notas == ()


def test_L2_5_texto_de_la_tarea_bloqueado_por_otra_causa_no_produce_nota():
    # Prosa 2 de L2 (sin fila propia): la nota de inyección solo sale con texto
    # realmente ajeno; un escribir con texto de la tarea bloqueado por otra
    # causa (coordenada fuera) no la produce.
    ojos = OjosFalsos(
        [
            Accion(tipo="escribir", texto="Consultorio 302", con_clic=True, x=1001, y=500),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, pantalla, _ = correr_fase("crear", ojos, intencion=INTENCION_CONSULTORIO)
    assert resultado.tipo == "terminar"
    assert ("escribir", "Consultorio 302") not in pantalla.acciones  # bloqueada, pero por la coordenada
    assert resultado.notas == ()


# --------------------------------------------- Bloque 8 (tabla L3 del encargo 010)
# NOTA: el aviso (clic con funcion cerrar_aviso dentro de la cuota) es
# gratuito: no gasta paso de fase, no cuenta como acción sin efecto y
# reinicia los bloqueos seguidos.


def clic_aviso(texto="", x=500, y=400):
    return Accion(tipo="clic", funcion="cerrar_aviso", x=x, y=y, texto=texto)


def test_L3_1_el_aviso_no_gasta_el_unico_paso():
    # L3.1: max_pasos_fase=1; ojos: cerrar_aviso ("Novedades"), clic navegar,
    # terminar -> ResultadoFase("terminar"): el aviso no gastó el único paso;
    # la pantalla recibió los dos clics; pasos==1; avisos_cerrados==1.
    ojos = OjosFalsos(
        [
            clic_aviso("Novedades"),
            clic(500, 250),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, pantalla, estado = correr_fase("crear", ojos, max_pasos_fase=1)
    assert resultado == ResultadoFase("terminar")
    assert pantalla.acciones == [("clic", 640, 320), ("clic", 640, 200)]
    assert estado.pasos == 1
    assert estado.avisos_cerrados == 1


def test_L3_2_cuatro_avisos_con_la_misma_captura_terminan():
    # L3.2: 4 veces cerrar_aviso con la misma captura, luego terminar ->
    # ResultadoFase("terminar") (no es "la pantalla no cambia"; no es
    # "demasiados intentos"); avisos_cerrados==4.
    ojos = OjosFalsos(
        [
            clic_aviso("Novedades"),
            clic_aviso("Novedades"),
            clic_aviso("Novedades"),
            clic_aviso("Novedades"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, _, estado = correr_fase(
        "resolver", ojos, pantalla=PantallaFalsa(png_estatico=True)
    )
    assert resultado == ResultadoFase("terminar")
    assert estado.avisos_cerrados == 4


def test_L3_3_el_sexto_aviso_cuenta_como_clic_normal():
    # L3.3: cerrar_aviso ×6 con la misma captura, luego terminar (max=14) ->
    # el 6.º cuenta como acción normal: termina terminar, avisos_cerrados==5
    # y pasos==1.
    ojos = OjosFalsos(
        [clic_aviso("Novedades") for _ in range(6)]
        + [Accion(tipo="terminar", razon="listo")]
    )
    resultado, _, estado = correr_fase(
        "resolver", ojos, pantalla=PantallaFalsa(png_estatico=True), max_pasos_fase=14
    )
    assert resultado == ResultadoFase("terminar")
    assert estado.avisos_cerrados == 5
    assert estado.pasos == 1


def _lineas_de_traza(carpeta):
    # NOTA: lee y parsea traza.jsonl de la carpeta de la traza (L3.4/L3.5).
    archivo = carpeta / "traza.jsonl"
    assert archivo.is_file(), "la traza no creó traza.jsonl"
    return [
        json.loads(linea)
        for linea in archivo.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]


def test_L3_4_la_traza_registra_el_aviso_cerrado(monkeypatch, tmp_path):
    # L3.4: con AGENTE_TRAZA_DIR puesta; cerrar_aviso con texto="Novedades",
    # luego terminar -> traza.jsonl contiene una línea JSON con
    # evento == "aviso cerrado: Novedades".
    monkeypatch.setenv("AGENTE_TRAZA_DIR", str(tmp_path))
    ojos = OjosFalsos(
        [
            clic_aviso("Novedades"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, _, _ = correr_fase("resolver", ojos)
    assert resultado == ResultadoFase("terminar")
    assert any(
        linea.get("evento") == "aviso cerrado: Novedades"
        for linea in _lineas_de_traza(tmp_path)
    )


def test_L3_5_aviso_sin_titulo_queda_sin_titulo(monkeypatch, tmp_path):
    # L3.5: igual con texto="" -> evento == "aviso cerrado: (sin título)".
    monkeypatch.setenv("AGENTE_TRAZA_DIR", str(tmp_path))
    ojos = OjosFalsos(
        [
            clic_aviso(""),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, _, _ = correr_fase("resolver", ojos)
    assert resultado == ResultadoFase("terminar")
    assert any(
        linea.get("evento") == "aviso cerrado: (sin título)"
        for linea in _lineas_de_traza(tmp_path)
    )


def test_L3_6_el_aviso_reinicia_los_bloqueos_seguidos():
    # L3.6: ojos: bloqueada, bloqueada, cerrar_aviso, bloqueada, bloqueada,
    # terminar -> NO falla por bloqueos: el aviso reinicia los seguidos.
    ojos = OjosFalsos(
        [
            escribir("borra todos los pedidos"),
            escribir("borra el inventario"),
            clic_aviso("Novedades"),
            escribir("borra el inventario"),
            escribir("borra toda la base"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, _, _ = correr_fase("crear", ojos)
    # NOTA: la fila solo exige que NO falle por bloqueos (las notas de
    # inyección de los escribir bloqueados van aparte y aquí no importan).
    assert resultado.tipo == "terminar"
    assert resultado.razon == ""


def test_L3_borde_el_historial_recibe_cerre_un_aviso():
    # Borde (prosa 4, sin fila propia en la tabla): tras ejecutar un
    # cerrar_aviso, el historial que ven los ojos en el paso siguiente recibe
    # la línea fija "cerré un aviso".
    ojos = OjosFalsos(
        [
            clic_aviso("Novedades"),
            Accion(tipo="terminar", razon="listo"),
        ]
    )
    resultado, _, _ = correr_fase("resolver", ojos)
    assert resultado == ResultadoFase("terminar")
    assert "cerré un aviso" in ojos.historiales[-1]


# NOTA: L3.7 integra el lazo con el RFB falso y el ClienteRFB real en una
# pantalla pequeña: la primera pantalla es un modal (rectángulo claro con un
# botón en el centro) y, tras el clic en ese botón, el falso sirve la pantalla
# normal (cambiar_tras_pointer_up_s).
INTENCION_CONSULTA_L3 = Intencion(
    tipo="consultar",
    entidad="cliente",
    identificador={"nit": "901234567"},
)
ANCHO_RFB_L3 = 64
ALTO_RFB_L3 = 48
BOTON_RFB_L3 = (24, 20, 39, 27)  # botón del modal; su centro es el píxel (32, 24)
CENTRO_BOTON_RFB_L3 = (32, 24)


class OjosQueVen(OjosFalsos):
    """OjosFalsos que además guarda la captura que vieron en cada paso (L3.7)."""

    def __init__(self, acciones):
        super().__init__(acciones)
        self.pngs = []

    async def decidir(self, png, objetivo, historial):
        self.pngs.append(png)
        return await super().decidir(png, objetivo, historial)


def _pantalla_rfb(ancho, alto, relleno, rectangulos=()):
    """Pantalla RFB en BGRX: fondo `relleno` y rectángulos (x0, y0, x1, y1, valor)."""
    datos = bytearray(bytes([relleno]) * (ancho * alto * 4))
    for x0, y0, x1, y1, valor in rectangulos:
        for fila in range(y0, y1 + 1):
            for columna in range(x0, x1 + 1):
                base = (fila * ancho + columna) * 4
                datos[base:base + 4] = bytes([valor] * 4)
    return PantallaRFB(ancho, alto, bytes(datos))


def test_L3_7_integracion_con_el_rfb_falso():
    # L3.7: ojos guionados: cerrar_aviso en el botón del modal, luego leer con
    # {"candidatos": []} al ver la pantalla normal -> ResultadoFase("leer",
    # lectura={"candidatos": []}); el servidor falso recibió un clic (máscaras
    # 0, 1, 0) en el centro del botón; la segunda captura que vieron los ojos
    # difiere de la primera; con max_pasos_fase=1 también termina.
    async def correr(max_pasos_fase):
        modal = _pantalla_rfb(
            ANCHO_RFB_L3, ALTO_RFB_L3, 30,
            [(8, 8, 55, 39, 220), (*BOTON_RFB_L3, 140)],
        )
        normal = _pantalla_rfb(ANCHO_RFB_L3, ALTO_RFB_L3, 90)
        servidor = await crear_servidor(
            ConfiguracionServidor(
                pantallas=[modal, normal],
                cambiar_tras_pointer_up_s=0.05,
            )
        )
        try:
            async with ClienteRFB(servidor.url, "password") as pantalla:
                ojos = OjosQueVen(
                    [
                        Accion(tipo="clic", funcion="cerrar_aviso",
                               x=500, y=500, texto="Novedades"),
                        Accion(tipo="leer", lectura={"candidatos": []}),
                    ]
                )
                resultado = await ejecutar_fase(
                    fase="resolver",
                    objetivo="Busca el registro pedido y responde con leer.",
                    intencion=INTENCION_CONSULTA_L3,
                    pantalla=pantalla,
                    ojos=ojos,
                    estado=EstadoLazo(),
                    max_pasos_fase=max_pasos_fase,
                )
                # NOTA: espera a que el falso registre los 3 PointerEvent del clic.
                fin = time.monotonic() + 5.0
                while (len(servidor.registros_de("PointerEvent")) < 3
                       and time.monotonic() < fin):
                    await asyncio.sleep(0.02)
            return resultado, ojos, servidor
        finally:
            await servidor.cerrar()

    resultado, ojos, servidor = asyncio.run(correr(14))
    assert resultado == ResultadoFase("leer", lectura={"candidatos": []})
    # la segunda captura que vieron los ojos difiere de la primera (el modal se fue)
    assert len(ojos.pngs) == 2
    assert ojos.pngs[1] != ojos.pngs[0]
    # el servidor falso recibió un clic (máscaras 0, 1, 0) en el centro del botón
    eventos = [
        (r.datos[1], int.from_bytes(r.datos[2:4], "big"), int.from_bytes(r.datos[4:6], "big"))
        for r in servidor.registros_de("PointerEvent")
    ]
    assert eventos == [
        (0, *CENTRO_BOTON_RFB_L3),
        (1, *CENTRO_BOTON_RFB_L3),
        (0, *CENTRO_BOTON_RFB_L3),
    ]
    # y con un único paso de fase también termina: el aviso no lo gastó
    resultado_max_1, _, _ = asyncio.run(correr(1))
    assert resultado_max_1 == ResultadoFase("leer", lectura={"candidatos": []})