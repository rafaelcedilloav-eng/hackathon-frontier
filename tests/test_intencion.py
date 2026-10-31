"""Pruebas de frontier_agente.intencion · tabla I del encargo 004 (una prueba por fila)."""
from frontier_agente.intencion import validar_intencion
from frontier_agente.tipos_agente import Intencion

TAREA_I1 = "Registra al cliente Tienda Sol, NIT 901234567, ciudad Cali."
TAREA_I6 = "Corrige la dirección del cliente Casa Norte: ahora es Calle 80 # 24-15."
CRUDO_I1 = {
    "tipo": "crear",
    "entidad": "cliente",
    "identificador": {"nit": "901234567"},
    "campos": {"nombre": "Tienda Sol", "nit": "901234567", "ciudad": "Cali"},
}


def test_i1_crear_valido():
    r = validar_intencion(CRUDO_I1, TAREA_I1)
    assert r == Intencion(
        tipo="crear",
        entidad="cliente",
        identificador={"nit": "901234567"},
        campos={"nombre": "Tienda Sol", "nit": "901234567", "ciudad": "Cali"},
        motivo_fallo="",
        peligrosa=False,
    )


def test_i2_crear_sin_identificador_toma_la_llave_unica():
    # Sin identificador del modelo, el código decide: el primer campo con
    # llave de identificación única (nit) gana sobre el primer par (nombre).
    crudo = {k: v for k, v in CRUDO_I1.items() if k != "identificador"}
    r = validar_intencion(crudo, TAREA_I1)
    assert r.identificador == {"nit": "901234567"}
    assert r.motivo_fallo == ""


def test_i3_numero_se_vuelve_texto_sin_decimales():
    crudo = {
        "tipo": "crear",
        "entidad": "cliente",
        "identificador": {"nit": 901234567},
        "campos": {"nombre": "Tienda Sol", "nit": 901234567, "ciudad": "Cali"},
    }
    r = validar_intencion(crudo, TAREA_I1)
    assert r.identificador == {"nit": "901234567"}
    assert r.campos["nit"] == "901234567"
    assert r.motivo_fallo == ""


def test_i4_valor_que_no_esta_en_la_tarea():
    crudo = {
        "tipo": "crear",
        "entidad": "cliente",
        "identificador": {"nit": "901234567"},
        "campos": {"nombre": "Tienda Sol", "nit": "901234567", "ciudad": "Medellín"},
    }
    r = validar_intencion(crudo, TAREA_I1)
    assert "Medellín" in r.motivo_fallo


def test_i5_telefono_con_separadores_coincide_por_digitos():
    crudo = {"tipo": "crear", "campos": {"telefono": "315 765 4321"}}
    r = validar_intencion(crudo, "Crea cliente con teléfono 3157654321")
    assert r.motivo_fallo == ""
    assert r.peligrosa is False


def test_i6_modificar_valido():
    crudo = {
        "tipo": "modificar",
        "entidad": "cliente",
        "identificador": {"nombre": "Casa Norte"},
        "campos": {"direccion": "Calle 80 # 24-15"},
    }
    r = validar_intencion(crudo, TAREA_I6)
    assert r.motivo_fallo == ""
    assert r.tipo == "modificar"


def test_i7_modificar_sin_identificador():
    crudo = {
        "tipo": "modificar",
        "identificador": {},
        "campos": {"direccion": "Calle 80 # 24-15"},
    }
    r = validar_intencion(crudo, TAREA_I6)
    assert "no dice qué registro" in r.motivo_fallo


def test_i8_modificar_sin_campos():
    crudo = {
        "tipo": "modificar",
        "identificador": {"nombre": "Casa Norte"},
        "campos": {},
    }
    r = validar_intencion(crudo, TAREA_I6)
    assert "no dice qué cambiar" in r.motivo_fallo


def test_i9_tarea_destructiva_borra():
    r = validar_intencion({"tipo": "otro"}, "Borra todos los pedidos entregados")
    assert r.peligrosa is True
    assert r.motivo_fallo == "la tarea pide una acción destructiva"


def test_i10_tarea_destructiva_anula_con_crudo_valido():
    crudo = {"tipo": "consultar", "pregunta": "cuál es el total de la factura 123"}
    r = validar_intencion(crudo, "Anula la factura 123")
    assert r.peligrosa is True


def test_i11_borrego_no_es_borra():
    tarea = "Registra al cliente Borrego S.A., NIT 800111222"
    crudo = {
        "tipo": "crear",
        "entidad": "cliente",
        "campos": {"nombre": "Borrego S.A.", "nit": "800111222"},
    }
    r = validar_intencion(crudo, tarea)
    assert r.peligrosa is False
    assert r.motivo_fallo == ""


def test_i12_tipo_desconocido():
    r = validar_intencion({"tipo": "volar"}, "haz algo")
    assert r.tipo == "otro"
    assert r.motivo_fallo != ""


def test_i13_crudo_no_es_dict():
    r = validar_intencion("no soy un dict", "haz algo")
    assert r.tipo == "otro"
    assert r.motivo_fallo != ""


def test_i14_consultar_valida():
    crudo = {
        "tipo": "consultar",
        "pregunta": "¿Cuántas facturas vencidas tiene Casa Norte?",
        "identificador": {"nombre": "Casa Norte"},
    }
    tarea = "Consulta: ¿Cuántas facturas vencidas tiene Casa Norte?"
    r = validar_intencion(crudo, tarea)
    assert r.motivo_fallo == ""


def test_i15_consultar_sin_pregunta():
    r = validar_intencion({"tipo": "consultar", "pregunta": ""}, "cuéntame")
    assert r.motivo_fallo != ""


def test_i16_exportar_con_filtros():
    crudo = {"tipo": "exportar", "filtros": {"estado": "Entregado"}}
    tarea = "Exporta los pedidos Entregado de septiembre"
    r = validar_intencion(crudo, tarea)
    assert r.motivo_fallo == ""


def test_i17_otro_no_soportado():
    r = validar_intencion({"tipo": "otro"}, "algo raro")
    assert r.motivo_fallo == "tipo de tarea no soportado"


def test_i18_identificador_raro_del_modelo_se_descarta():
    # La llave razon_social no está en campos: se descarta y el código decide
    # con la llave única (nit); un identificador raro nunca hace fallar un crear.
    crudo = {
        "tipo": "crear",
        "entidad": "cliente",
        "identificador": {"razon_social": "Tienda Sol"},
        "campos": {"nombre": "Tienda Sol", "nit": "901234567"},
    }
    r = validar_intencion(crudo, "Registra al cliente Tienda Sol, NIT 901234567.")
    assert r.identificador == {"nit": "901234567"}
    assert r.motivo_fallo == ""


def test_i19_sin_llave_unica_usa_el_primer_par():
    crudo = {"tipo": "crear", "campos": {"nombre": "Tienda Sol", "ciudad": "Cali"}}
    r = validar_intencion(crudo, "Registra al cliente Tienda Sol, ciudad Cali.")
    assert r.identificador == {"nombre": "Tienda Sol"}


def test_i20_la_llave_unica_manda_sobre_el_modelo():
    # El modelo dijo telefono, pero nit es llave de identificación única:
    # el código decide y la llave única gana sobre el identificador del modelo.
    crudo = {
        "tipo": "crear",
        "entidad": "cliente",
        "identificador": {"telefono": "3157654321"},
        "campos": {
            "nombre": "Tienda Sol",
            "nit": "901234567",
            "telefono": "3157654321",
        },
    }
    tarea = "Registra al cliente Tienda Sol, NIT 901234567, teléfono 3157654321."
    r = validar_intencion(crudo, tarea)
    assert r.identificador == {"nit": "901234567"}
