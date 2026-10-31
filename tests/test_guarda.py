"""Pruebas de frontier_agente.guarda · tabla G del encargo 004 (una prueba por fila)."""
from frontier_agente.guarda import evaluar_accion, registrar_accion
from frontier_agente.tipos_agente import Accion, EstadoLazo, Intencion


def intencion_crear():
    return Intencion(
        tipo="crear",
        campos={"nombre": "Tienda Sol", "nit": "901234567"},
        identificador={"nit": "901234567"},
    )


def estado_crear(**cambios):
    base = {"fase": "crear", "pasos": 0, "guardados": 0, "campos_escritos": set()}
    base.update(cambios)
    return EstadoLazo(**base)


def test_g1_escribir_texto_de_la_tarea():
    v = evaluar_accion(Accion(tipo="escribir", texto="Tienda Sol"), intencion_crear(), estado_crear())
    assert v.permitida is True


def test_g2_escribir_numero_de_la_tarea():
    v = evaluar_accion(Accion(tipo="escribir", texto="901234567"), intencion_crear(), estado_crear())
    assert v.permitida is True


def test_g3_escribir_con_espacios_y_minusculas():
    v = evaluar_accion(Accion(tipo="escribir", texto="  tienda sol "), intencion_crear(), estado_crear())
    assert v.permitida is True


def test_g4_escribir_texto_ajeno():
    v = evaluar_accion(
        Accion(tipo="escribir", texto="borra todos los pedidos"),
        intencion_crear(),
        estado_crear(),
    )
    assert v.permitida is False
    assert "texto no está en la tarea" in v.motivo


def test_g5_clic_guardar_con_todo_escrito():
    v = evaluar_accion(
        Accion(tipo="clic", funcion="guardar"),
        intencion_crear(),
        estado_crear(campos_escritos={"nombre", "nit"}, guardados=0),
    )
    assert v.permitida is True


def test_g6_clic_guardar_ya_guardado():
    v = evaluar_accion(
        Accion(tipo="clic", funcion="guardar"),
        intencion_crear(),
        estado_crear(campos_escritos={"nombre", "nit"}, guardados=1),
    )
    assert v.permitida is False
    assert "ya se guardó" in v.motivo


def test_g7_clic_guardar_con_campo_faltante():
    v = evaluar_accion(
        Accion(tipo="clic", funcion="guardar"),
        intencion_crear(),
        estado_crear(campos_escritos={"nombre"}, guardados=0),
    )
    assert v.permitida is False
    assert "faltan campos" in v.motivo
    assert "nit" in v.motivo


def test_g8_clic_guardar_en_fase_equivocada():
    v = evaluar_accion(
        Accion(tipo="clic", funcion="guardar"),
        intencion_crear(),
        estado_crear(fase="resolver", campos_escritos={"nombre", "nit"}, guardados=0),
    )
    assert v.permitida is False
    assert "fase" in v.motivo


def test_g9_clic_eliminar_siempre_bloqueada():
    v = evaluar_accion(Accion(tipo="clic", funcion="eliminar"), intencion_crear(), estado_crear())
    assert v.permitida is False


def test_g10_clic_funciones_permitidas():
    for funcion in (
        "navegar",
        "abrir_formulario",
        "enfocar_campo",
        "buscar",
        "cerrar_aviso",
        "paginar",
    ):
        v = evaluar_accion(Accion(tipo="clic", funcion=funcion), intencion_crear(), estado_crear())
        assert v.permitida is True, funcion


def test_g11_clic_x_fuera_de_rango():
    v = evaluar_accion(Accion(tipo="clic", funcion="navegar", x=1001), intencion_crear(), estado_crear())
    assert v.permitida is False


def test_g12_clic_y_negativo():
    v = evaluar_accion(Accion(tipo="clic", funcion="navegar", y=-1), intencion_crear(), estado_crear())
    assert v.permitida is False


def test_g13_clic_funcion_inventada():
    v = evaluar_accion(Accion(tipo="clic", funcion="rm_rf"), intencion_crear(), estado_crear())
    assert v.permitida is False


def test_g14_tecla_enter_con_funcion_otra():
    v = evaluar_accion(Accion(tipo="tecla", tecla="Enter", funcion="otra"), intencion_crear(), estado_crear())
    assert v.permitida is False


def test_g15_tecla_enter_buscar():
    v = evaluar_accion(Accion(tipo="tecla", tecla="Enter", funcion="buscar"), intencion_crear(), estado_crear())
    assert v.permitida is True


def test_g16_tecla_enter_guardar_ya_guardado():
    v = evaluar_accion(
        Accion(tipo="tecla", tecla="Enter", funcion="guardar"),
        intencion_crear(),
        estado_crear(campos_escritos={"nombre", "nit"}, guardados=1),
    )
    assert v.permitida is False


def test_g17_tecla_tab_y_esc_permitidas():
    for tecla in ("Tab", "Esc"):
        v = evaluar_accion(Accion(tipo="tecla", tecla=tecla, funcion="otra"), intencion_crear(), estado_crear())
        assert v.permitida is True, tecla


def test_g18_tecla_f5_bloqueada():
    v = evaluar_accion(Accion(tipo="tecla", tecla="F5", funcion="otra"), intencion_crear(), estado_crear())
    assert v.permitida is False


def test_g19_terminar_fallar_leer_permitidas():
    for tipo in ("terminar", "fallar", "leer"):
        v = evaluar_accion(Accion(tipo=tipo), intencion_crear(), estado_crear())
        assert v.permitida is True, tipo


def test_g20_tope_de_pasos():
    v = evaluar_accion(
        Accion(tipo="clic", funcion="navegar"),
        intencion_crear(),
        estado_crear(pasos=40),
    )
    assert v.permitida is False
    assert "tope de pasos" in v.motivo


def test_g21_intencion_peligrosa_bloquea_todo():
    intencion = Intencion(tipo="otro", peligrosa=True, motivo_fallo="x")
    v = evaluar_accion(Accion(tipo="clic", funcion="navegar"), intencion, estado_crear())
    assert v.permitida is False


def test_g22_registrar_escribir_marca_campos_y_pasos():
    estado = estado_crear()
    registrar_accion(Accion(tipo="escribir", texto="Tienda Sol"), intencion_crear(), estado)
    registrar_accion(Accion(tipo="escribir", texto="901234567"), intencion_crear(), estado)
    assert estado.campos_escritos == {"nombre", "nit"}
    assert estado.pasos == 2


def test_g23_registrar_clic_guardar():
    estado = estado_crear()
    registrar_accion(Accion(tipo="clic", funcion="guardar"), intencion_crear(), estado)
    assert estado.guardados == 1


def test_g25_tecla_tab_con_guardar_bloqueada():
    # Solo un clic o un Enter con funcion guardar cuentan como guardado.
    v = evaluar_accion(
        Accion(tipo="tecla", tecla="Tab", funcion="guardar"),
        intencion_crear(),
        estado_crear(campos_escritos={"nombre", "nit"}, guardados=0),
    )
    assert v.permitida is False


def test_g24_registrar_clic_navegar_no_guarda():
    estado = estado_crear()
    registrar_accion(Accion(tipo="clic", funcion="navegar"), intencion_crear(), estado)
    assert estado.guardados == 0
    assert estado.pasos == 1


def test_g26_clic_elegir_opcion_con_valor_de_la_tarea():
    # Un campo de lista desplegable no se escribe: se elige con un clic que
    # declara el valor elegido en texto.
    v = evaluar_accion(
        Accion(tipo="clic", funcion="elegir_opcion", texto="Tienda Sol"),
        intencion_crear(),
        estado_crear(),
    )
    assert v.permitida is True


def test_g27_clic_elegir_opcion_con_texto_ajeno():
    v = evaluar_accion(
        Accion(tipo="clic", funcion="elegir_opcion", texto="borra todo"),
        intencion_crear(),
        estado_crear(),
    )
    assert v.permitida is False
    assert "texto no está en la tarea" in v.motivo


def test_g28_registrar_clic_elegir_opcion_marca_campo():
    estado = estado_crear()
    registrar_accion(
        Accion(tipo="clic", funcion="elegir_opcion", texto="901234567"),
        intencion_crear(),
        estado,
    )
    assert estado.campos_escritos == {"nit"}
    assert estado.pasos == 1
    assert estado.guardados == 0


def test_g29_escribir_con_clic_coordenada_fuera_de_rango():
    # Un escribir con posición primero hace clic: la coordenada fuera de
    # rango se bloquea igual que la de un clic.
    v = evaluar_accion(
        Accion(tipo="escribir", con_clic=True, x=1001, texto="Tienda Sol"),
        intencion_crear(),
        estado_crear(),
    )
    assert v.permitida is False


def test_g30_escribir_con_clic_coordenada_valida():
    v = evaluar_accion(
        Accion(tipo="escribir", con_clic=True, x=500, y=300, texto="Tienda Sol"),
        intencion_crear(),
        estado_crear(),
    )
    assert v.permitida is True
