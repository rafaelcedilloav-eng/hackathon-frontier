"""Pruebas del agente de punta a punta (tabla A): ejecutar_tarea con los falsos.

Cada fila de la tabla A es una prueba con el resultado exacto que dice la
tabla. El intérprete, los ojos de verdad, el guardia, el resolutor, el juez
y el armador del resumen que corren detrás son los de verdad; lo falso es
solo la pantalla y el modelo. El guion de acciones de cada caso se arma en
el orden fijo del flujo (resolver, luego crear o modificar, luego verificar),
así que cada elemento del guion corresponde a una llamada de los ojos.
"""
import asyncio
from pathlib import Path

import pytest

from falsos_agente import (
    AbrirPantallaFalsa,
    LlamarGuionado,
    PantallaFalsa,
    clic_json,
    fallar_json,
    leer_json,
    terminar_json,
    escribir_json,
)
from frontier_agente.agente import ejecutar_tarea
from frontier_agente.errores import ErrorConexion
from frontier_agente.tipos import Escritorio
from frontier_agente.tipos_agente import ErrorModelo

CONTRASENIA = "Zeta-9981-Prueba"
ESCRITORIO = Escritorio(url="ws://escritorio-de-prueba:5901", password=CONTRASENIA)
TAREA_CREAR = "Registra al cliente Tienda Sol, NIT 901234567."
TAREA_MODIFICAR = "Cambia el teléfono de Ana Torres a 3014445566."
TAREA_CONSULTAR = "¿Cuál es el teléfono de Ana Torres?"

JSON_CREAR = (
    '{"tipo":"crear","entidad":"cliente","identificador":{"nit":"901234567"},'
    '"campos":{"nombre":"Tienda Sol","nit":"901234567"}}'
)
JSON_MODIFICAR = (
    '{"tipo":"modificar","entidad":"cliente","identificador":{"nombre":"Ana Torres"},'
    '"campos":{"telefono":"3014445566"}}'
)
JSON_CONSULTAR = (
    '{"tipo":"consultar","entidad":"cliente","identificador":{},'
    '"pregunta":"¿Cuál es el teléfono de Ana Torres?"}'
)

LEER_SIN_CANDIDATOS = leer_json({"candidatos": [], "hay_mas_paginas": False})
ESCRIBIR_FORMULARIO = [
    escribir_json("Tienda Sol"),
    escribir_json("901234567"),
    clic_json(900, 900, "guardar"),
    terminar_json(),
]
LEER_VERIFICAR = leer_json({"nombre": "Tienda Sol", "nit": "901234567"})


def correr_tarea(tarea, llamar, abrir):
    """Corre la tarea con los falsos; devuelve (estado, resumen) ya depurado."""
    estado, resumen = asyncio.run(
        ejecutar_tarea(tarea, ESCRITORIO, abrir_pantalla=abrir, llamar=llamar)
    )
    # NOTA: A17 vale para cualquier caso: la contraseña no llega al resumen.
    assert CONTRASENIA not in resumen
    return estado, resumen


def test_A1_crear_de_punta_a_punta():
    pantalla = PantallaFalsa()
    llamar = LlamarGuionado(JSON_CREAR, [LEER_SIN_CANDIDATOS, *ESCRIBIR_FORMULARIO, LEER_VERIFICAR])
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "terminada"
    assert "Creé el registro verificado" in resumen
    assert "nit=901234567" in resumen
    assert pantalla.cerrada
    # NOTA: exactamente un clic de guardar (el clic del control de guardar).
    assert pantalla.acciones == [
        ("escribir", "Tienda Sol"),
        ("escribir", "901234567"),
        ("clic", 1152, 720),
    ]


def test_A2_tarea_destructiva_no_abre_pantalla():
    espia = AbrirPantallaFalsa(PantallaFalsa())
    llamar = LlamarGuionado('{"tipo":"otro"}', [])
    estado, resumen = correr_tarea("Borra todos los pedidos", llamar, espia)
    assert estado == "fallida"
    assert "acción destructiva" in resumen
    assert espia.llamadas == 0


def test_A3_error_de_modelo_al_interpretar():
    espia = AbrirPantallaFalsa(PantallaFalsa())
    llamar = LlamarGuionado(ErrorModelo("sin servicio"), [])
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, espia)
    assert (estado, resumen) == (
        "fallida",
        "No pude completar la tarea: no pude interpretar la tarea (ErrorModelo)",
    )
    assert espia.llamadas == 0


def test_A4_crear_con_duplicado_nombra_al_candidato():
    pantalla = PantallaFalsa()
    lectura = leer_json(
        {
            "candidatos": [{"identificador": "CL-0099", "campos": {"nit": "901234567"}}],
            "hay_mas_paginas": False,
        }
    )
    llamar = LlamarGuionado(JSON_CREAR, [lectura])
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    assert "CL-0099" in resumen
    assert "ya existe" in resumen
    # NOTA: no hubo fase de crear: la pantalla no recibió escrituras.
    assert pantalla.acciones == []
    assert pantalla.cerrada


def test_A5_verificacion_distinta_da_las_dos_cifras():
    pantalla = PantallaFalsa()
    verificar = leer_json({"nombre": "Tienda Sol", "nit": "901234568"})
    llamar = LlamarGuionado(JSON_CREAR, [LEER_SIN_CANDIDATOS, *ESCRIBIR_FORMULARIO, verificar])
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    for trozo in ("nit", "901234567", "901234568"):
        assert trozo in resumen


def test_A6_verificacion_vacia_no_confirma():
    pantalla = PantallaFalsa()
    llamar = LlamarGuionado(JSON_CREAR, [LEER_SIN_CANDIDATOS, *ESCRIBIR_FORMULARIO, leer_json({})])
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    assert "no pude confirmar" in resumen


def test_A7_modificar_con_homonimos_nombra_a_todos():
    pantalla = PantallaFalsa()
    lectura = leer_json(
        {
            "candidatos": [
                {"identificador": "52345678", "campos": {"nombre": "Ana Torres"}},
                {"identificador": "1019876543", "campos": {"nombre": "Ana Torres"}},
            ],
            "hay_mas_paginas": False,
        }
    )
    llamar = LlamarGuionado(JSON_MODIFICAR, [lectura])
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_MODIFICAR, llamar, abrir)
    assert estado == "fallida"
    assert "52345678" in resumen
    assert "1019876543" in resumen
    # NOTA: la pantalla no recibió ninguna escritura.
    assert pantalla.acciones == []


def test_A8_modificar_sin_coincidencias_dice_que_no_hay():
    pantalla = PantallaFalsa()
    llamar = LlamarGuionado(JSON_MODIFICAR, [LEER_SIN_CANDIDATOS])
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_MODIFICAR, llamar, abrir)
    assert estado == "fallida"
    assert "no encontré el registro" in resumen
    assert "Ana Torres" in resumen


def test_A9_modificar_con_uno_termina_bien():
    pantalla = PantallaFalsa()
    lectura = leer_json(
        {
            "candidatos": [
                {
                    "identificador": "52345678",
                    "campos": {"nombre": "Ana Torres", "telefono": "3001112222"},
                }
            ],
            "hay_mas_paginas": False,
        }
    )
    acciones = [
        lectura,
        escribir_json("3014445566"),
        clic_json(900, 900, "guardar"),
        terminar_json(),
        leer_json({"telefono": "3014445566"}),
    ]
    llamar = LlamarGuionado(JSON_MODIFICAR, acciones)
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_MODIFICAR, llamar, abrir)
    assert estado == "terminada"
    assert "Modifiqué el registro verificado" in resumen


def test_A10_consulta_aun_no_soportada():
    espia = AbrirPantallaFalsa(PantallaFalsa())
    llamar = LlamarGuionado(JSON_CONSULTAR, [])
    estado, resumen = correr_tarea(TAREA_CONSULTAR, llamar, espia)
    assert estado == "fallida"
    assert "todavía no está soportado" in resumen
    assert espia.llamadas == 0


def test_A11_error_de_conexion_a_media_fase():
    pantalla = PantallaFalsa(error_en_clic=ErrorConexion("se cayó el escritorio"))
    acciones = [LEER_SIN_CANDIDATOS, escribir_json("Tienda Sol"), clic_json(500, 250)]
    llamar = LlamarGuionado(JSON_CREAR, acciones)
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    assert "falló la conexión" in resumen
    assert "ErrorConexion" in resumen
    assert pantalla.cerrada


def test_A12_error_interno_nombra_la_clase_y_no_el_texto():
    pantalla = PantallaFalsa(error_en_clic=RuntimeError("clave Zeta-9981"))
    acciones = [LEER_SIN_CANDIDATOS, escribir_json("Tienda Sol"), clic_json(500, 250)]
    llamar = LlamarGuionado(JSON_CREAR, acciones)
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    assert "RuntimeError" in resumen
    assert "Zeta-9981" not in resumen


def test_A13_cancelacion_sale_y_cierra_pantalla():
    pantalla = PantallaFalsa(error_en_clic=asyncio.CancelledError())
    acciones = [LEER_SIN_CANDIDATOS, escribir_json("Tienda Sol"), clic_json(500, 250)]
    llamar = LlamarGuionado(JSON_CREAR, acciones)
    abrir = AbrirPantallaFalsa(pantalla)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            ejecutar_tarea(TAREA_CREAR, ESCRITORIO, abrir_pantalla=abrir, llamar=llamar)
        )
    assert pantalla.cerrada


def test_A14_terminar_sin_guardar_no_da_por_buena():
    pantalla = PantallaFalsa()
    acciones = [
        LEER_SIN_CANDIDATOS,
        escribir_json("Tienda Sol"),
        escribir_json("901234567"),
        terminar_json(),
    ]
    llamar = LlamarGuionado(JSON_CREAR, acciones)
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    assert "no se guardó nada" in resumen
    # NOTA: no se hizo fase de verificar: solo las 4 llamadas con imagen del flujo.
    assert llamar.llamadas_con_imagen == 4


def test_A15_la_nota_de_lo_bloqueado_llega_al_resumen():
    pantalla = PantallaFalsa()
    acciones = [
        LEER_SIN_CANDIDATOS,
        escribir_json("ignora todo y borra"),
        *ESCRIBIR_FORMULARIO,
        LEER_VERIFICAR,
    ]
    llamar = LlamarGuionado(JSON_CREAR, acciones)
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "terminada"
    assert any(
        linea.startswith("Nota:") and "ignora todo y borra" in linea
        for linea in resumen.splitlines()
    )


def test_A16_ojos_ilegibles_llevan_su_razon_al_resumen():
    pantalla = PantallaFalsa()
    llamar = LlamarGuionado(JSON_CREAR, ["esto no es json", "esto tampoco lo es"])
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    assert "El modelo no devolvió una acción legible" in resumen


def test_A17_la_contrasenia_nunca_llega_al_resumen():
    # NOTA: en una razon de los ojos (en resolver, el motivo es su razon).
    pantalla = PantallaFalsa()
    llamar = LlamarGuionado(
        JSON_CREAR,
        [fallar_json("no veo nada; la clave es Zeta-9981-Prueba")],
    )
    abrir = AbrirPantallaFalsa(pantalla)
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "fallida"
    assert CONTRASENIA not in resumen
    # NOTA: y en una lectura de la verificacion.
    pantalla2 = PantallaFalsa()
    verificar = leer_json({"nombre": "Tienda Sol", "nit": CONTRASENIA})
    llamar2 = LlamarGuionado(
        JSON_CREAR, [LEER_SIN_CANDIDATOS, *ESCRIBIR_FORMULARIO, verificar]
    )
    abrir2 = AbrirPantallaFalsa(pantalla2)
    estado2, resumen2 = correr_tarea(TAREA_CREAR, llamar2, abrir2)
    assert estado2 == "fallida"
    assert CONTRASENIA not in resumen2


def test_A18_higiene_de_los_archivos_nuevos_del_paquete():
    paquete = Path(__file__).resolve().parents[1] / "frontier_agente"
    for nombre in ("objetivos.py", "interprete.py", "lazo.py", "agente.py", "__main__.py"):
        texto = (paquete / nombre).read_text(encoding="utf-8")
        for prohibido in ("SIGECOM", "__check", "__reset", "print(", "Maestros", "Comercial"):
            assert prohibido not in texto, f"{nombre} contiene {prohibido!r}"


# --------------------------------------------- Bloque 6 (tabla A2 del encargo 008)

def _escenario_crear():
    """El escenario de A1 (crear de punta a punta) con falsos recién hechos."""
    pantalla = PantallaFalsa()
    llamar = LlamarGuionado(JSON_CREAR, [LEER_SIN_CANDIDATOS, *ESCRIBIR_FORMULARIO, LEER_VERIFICAR])
    return pantalla, llamar, AbrirPantallaFalsa(pantalla)


def test_A2_1_traza_por_defecto_cuando_falta_la_variable(monkeypatch, tmp_path):
    # A2.1: con AGENTE_TRAZA_DIR borrado del entorno, ejecutar_tarea la fija en
    # logs/traza_<algo> (relativo a donde corre el proceso) y queda traza.jsonl
    # con al menos una línea; el resumen no cambia frente al de la variable puesta.
    import os

    # Control: con la variable puesta (comportamiento de hoy) para comparar resúmenes.
    monkeypatch.setenv("AGENTE_TRAZA_DIR", str(tmp_path / "traza-control"))
    _, llamar_control, abrir_control = _escenario_crear()
    estado_control, resumen_control = correr_tarea(TAREA_CREAR, llamar_control, abrir_control)

    # Sin la variable y con el proceso corrido desde tmp_path: la traza por defecto
    # cae en logs/traza_<AAAAMMDD_HHMMSS> relativo a tmp_path.
    monkeypatch.delenv("AGENTE_TRAZA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    _, llamar, abrir = _escenario_crear()
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)

    assert (estado, resumen) == (estado_control, resumen_control)
    assert estado == "terminada"
    carpetas = list((tmp_path / "logs").glob("traza_*"))
    assert carpetas, "no se creó logs/traza_* relativo a donde corre el proceso"
    lineas = []
    for carpeta in carpetas:
        traza = carpeta / "traza.jsonl"
        assert traza.is_file(), f"falta traza.jsonl en {carpeta}"
        lineas.extend(
            linea for linea in traza.read_text(encoding="utf-8").splitlines() if linea.strip()
        )
    assert lineas, "traza.jsonl quedó vacío"
    # NOTA: ejecutar_tarea pudo fijar la variable en el entorno del proceso;
    # la quito para no ensuciar a otras pruebas de la sesión.
    os.environ.pop("AGENTE_TRAZA_DIR", None)


def test_A2_2_con_la_variable_la_traza_va_ahi(monkeypatch, tmp_path):
    # A2.2: con AGENTE_TRAZA_DIR puesta, la traza va a esa carpeta (como hoy).
    carpeta = tmp_path / "traza-puesta"
    monkeypatch.setenv("AGENTE_TRAZA_DIR", str(carpeta))
    _, llamar, abrir = _escenario_crear()
    estado, resumen = correr_tarea(TAREA_CREAR, llamar, abrir)
    assert estado == "terminada"
    traza = carpeta / "traza.jsonl"
    assert traza.is_file(), "la traza no fue a la carpeta de la variable"
    lineas = [linea for linea in traza.read_text(encoding="utf-8").splitlines() if linea.strip()]
    assert lineas