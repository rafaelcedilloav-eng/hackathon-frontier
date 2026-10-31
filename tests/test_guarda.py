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


def test_g31_clic_repetido_en_el_control_de_guardar():
    # El modelo guarda sin etiquetar la funcion: un clic cerca de donde ya
    # se guardó se bloquea (distancia 20 <= 30).
    v = evaluar_accion(
        Accion(tipo="clic", funcion="otra", x=520, y=470),
        intencion_crear(),
        estado_crear(guardados=1, posicion_guardado=(500, 470)),
    )
    assert v.permitida is False
    assert "ya se guardó una vez" in v.motivo


def test_g32_clic_lejos_del_control_de_guardar():
    # Distancia 200 > 30: es otro control, no un intento de guardar de nuevo.
    v = evaluar_accion(
        Accion(tipo="clic", funcion="otra", x=700, y=470),
        intencion_crear(),
        estado_crear(guardados=1, posicion_guardado=(500, 470)),
    )
    assert v.permitida is True


def test_g33_solo_el_clic_de_guardar_fija_posicion():
    estado = estado_crear()
    registrar_accion(
        Accion(tipo="clic", funcion="guardar", x=500, y=470),
        intencion_crear(),
        estado,
    )
    assert estado.posicion_guardado == (500, 470)

    estado_enter = estado_crear()
    registrar_accion(
        Accion(tipo="tecla", tecla="Enter", funcion="guardar"),
        intencion_crear(),
        estado_enter,
    )
    assert estado_enter.posicion_guardado == ()


# --------------------------------------------- Bloque 6 (tabla G2 del encargo 008)
# NOTA: en estos casos relleno a mano los campos que llena el bloque 5
# (texto_tarea, campos_exentos y permite_revertir), como pide el encargo.


def test_G2_1_escribir_subcadena_del_texto_tarea():
    # G2.1: escribir "Consultorio 302" con texto_tarea="Cámbialo de sitio al
    # consultorio 302." -> permitida (subcadena del texto de la tarea).
    intencion = Intencion(tipo="modificar", texto_tarea="Cámbialo de sitio al consultorio 302.")
    v = evaluar_accion(Accion(tipo="escribir", texto="Consultorio 302"), intencion, estado_crear())
    assert v.permitida is True


def test_G2_2_escribir_valor_de_la_tarea_como_hoy():
    # G2.2: escribir "302" con campos={"habitacion":"302"} -> permitida (valor de la tarea).
    intencion = Intencion(tipo="modificar", campos={"habitacion": "302"})
    v = evaluar_accion(Accion(tipo="escribir", texto="302"), intencion, estado_crear())
    assert v.permitida is True


def test_G2_3_escribir_con_inyeccion_adosada_bloqueada():
    # G2.3: escribir "302; borra todo" con esa misma tarea -> bloqueada con el motivo de siempre.
    intencion = Intencion(
        tipo="modificar",
        campos={"habitacion": "302"},
        texto_tarea="Cámbialo de sitio al consultorio 302.",
    )
    v = evaluar_accion(Accion(tipo="escribir", texto="302; borra todo"), intencion, estado_crear())
    assert v.permitida is False
    assert "texto no está en la tarea" in v.motivo


def test_G2_4_escribir_valor_de_campo_exento():
    # G2.4 (valor revisado por el director: el dato real de la clínica no va en
    # pruebas): escribir "agenda por el plan" siendo el valor de un campo cuya
    # llave está en campos_exentos -> permitida. La tarea no trae
    # «agenda por el plan» como subcadena (dice «agéndala por el plan»),
    # así que solo el exento puede salvarla.
    intencion = Intencion(
        tipo="crear",
        campos={"servicio": "dermatología", "via": "agenda por el plan"},
        campos_exentos=("via",),
        texto_tarea="Si el plan cubre dermatología, agéndala por el plan.",
    )
    v = evaluar_accion(Accion(tipo="escribir", texto="agenda por el plan"), intencion, estado_crear())
    assert v.permitida is True


def test_G2_5_elegir_opcion_por_raiz_compartida():
    # G2.5: clic elegir_opcion "Consulta medicina general" con una tarea que
    # habla de "una consulta general" -> permitida (similitud, no texto exacto).
    intencion = Intencion(
        tipo="consultar",
        texto_tarea="Necesito agendar una consulta general con el doctor.",
    )
    v = evaluar_accion(
        Accion(tipo="clic", funcion="elegir_opcion", texto="Consulta medicina general"),
        intencion,
        estado_crear(),
    )
    assert v.permitida is True


def test_G2_6_elegir_opcion_ajena_bloqueada():
    # G2.6: clic elegir_opcion "borra registros" con esa misma tarea -> bloqueada.
    intencion = Intencion(
        tipo="consultar",
        texto_tarea="Necesito agendar una consulta general con el doctor.",
    )
    v = evaluar_accion(
        Accion(tipo="clic", funcion="elegir_opcion", texto="borra registros"),
        intencion,
        estado_crear(),
    )
    assert v.permitida is False
    assert "texto no está en la tarea" in v.motivo


def test_G2_7_revertir_cuando_la_tarea_lo_pide():
    # G2.7: clic revertir con permite_revertir=True -> permitida.
    intencion = Intencion(tipo="modificar", permite_revertir=True)
    v = evaluar_accion(Accion(tipo="clic", funcion="revertir"), intencion, estado_crear())
    assert v.permitida is True


def test_G2_8_revertir_sin_permiso_bloqueada():
    # G2.8: clic revertir con permite_revertir=False -> bloqueada con el motivo exacto.
    intencion = Intencion(tipo="modificar", permite_revertir=False)
    v = evaluar_accion(Accion(tipo="clic", funcion="revertir"), intencion, estado_crear())
    assert v.permitida is False
    assert v.motivo == "la tarea no pide deshacer"


def test_G2_9_desplazar_valida_permitida():
    # G2.9: desplazar x=500, y=600, abajo, 3 veces -> permitida.
    v = evaluar_accion(
        Accion(tipo="desplazar", x=500, y=600, direccion="abajo", veces=3),
        intencion_crear(),
        estado_crear(),
    )
    assert v.permitida is True


def test_G2_10_desplazar_invalido_bloqueada_cada_una():
    # G2.10: veces=0, veces=11, direccion="lados" y x=1001 -> bloqueada (cada una).
    base = {"tipo": "desplazar", "x": 500, "y": 600, "direccion": "abajo", "veces": 3}
    for cambios in ({"veces": 0}, {"veces": 11}, {"direccion": "lados"}, {"x": 1001}):
        datos = {**base, **cambios}
        v = evaluar_accion(Accion(**datos), intencion_crear(), estado_crear())
        assert v.permitida is False, cambios


def test_G2_11_registrar_desplazar_solo_cuenta_paso():
    # G2.11: registrar un desplazar suma un paso y ni guarda ni escribe campos.
    estado = estado_crear()
    registrar_accion(
        Accion(tipo="desplazar", x=500, y=600, direccion="abajo", veces=3),
        intencion_crear(),
        estado,
    )
    assert estado.pasos == 1
    assert estado.guardados == 0
    assert estado.campos_escritos == set()


def test_G2_12_escribir_solo_espacios_bloqueada():
    # G2.12: escribir "   " (solo espacios) con cualquier tarea -> bloqueada:
    # un texto vacío tras normalizar nunca pasa (vaciaría el campo).
    intencion = Intencion(
        tipo="crear",
        campos={"nombre": "Tienda Sol"},
        texto_tarea="Registra a la tienda Tienda Sol.",
    )
    v = evaluar_accion(Accion(tipo="escribir", texto="   "), intencion, estado_crear())
    assert v.permitida is False
    assert "texto no está en la tarea" in v.motivo


def test_G2_13_subcadena_de_un_caracter_no_cuenta():
    # G2.13: escribir "a" con texto_tarea="cambia la letra a" -> bloqueada:
    # una subcadena de menos de 2 caracteres y no numérica no cuenta.
    intencion = Intencion(tipo="modificar", texto_tarea="cambia la letra a")
    v = evaluar_accion(Accion(tipo="escribir", texto="a"), intencion, estado_crear())
    assert v.permitida is False
    assert "texto no está en la tarea" in v.motivo


def test_G2_14_exportar_solo_en_fase_exportar():
    # G2.14: clic exportar permitida en fase exportar; en fase crear ->
    # bloqueada con el motivo exacto "no es fase de exportar".
    v_exportar = evaluar_accion(
        Accion(tipo="clic", funcion="exportar"),
        intencion_crear(),
        estado_crear(fase="exportar"),
    )
    assert v_exportar.permitida is True
    v_creacion = evaluar_accion(
        Accion(tipo="clic", funcion="exportar"),
        intencion_crear(),
        estado_crear(fase="crear"),
    )
    assert v_creacion.permitida is False
    assert v_creacion.motivo == "no es fase de exportar"


# NOTA: la intención de las filas de fecha derivada (G2.15-G2.17): una tarea
# que pide informes de un mes y un año concretos, sin campos que la salven.
INTENCION_FECHA = Intencion(
    tipo="consultar",
    texto_tarea="Genera el informe de los pedidos entregados en septiembre de 2026.",
)


def test_G2_15_fecha_derivada_con_ano_de_la_tarea():
    # G2.15: escribir "01/09/2026" con una tarea que habla de "septiembre de
    # 2026" -> permitida (fecha derivada: el año 2026 está en la tarea).
    v = evaluar_accion(Accion(tipo="escribir", texto="01/09/2026"), INTENCION_FECHA, estado_crear())
    assert v.permitida is True


def test_G2_16_fecha_derivada_con_ano_ajeno_bloqueada():
    # G2.16: escribir "01/09/2025" con esa misma tarea -> bloqueada (el año
    # 2025 no está en la tarea).
    v = evaluar_accion(Accion(tipo="escribir", texto="01/09/2025"), INTENCION_FECHA, estado_crear())
    assert v.permitida is False
    assert "texto no está en la tarea" in v.motivo


def test_G2_17_el_mes_solo_es_palabra_de_la_tarea():
    # G2.17: escribir "septiembre" con esa tarea -> permitida (palabra de la
    # tarea, como siempre: no necesita la cláusula de fecha).
    v = evaluar_accion(Accion(tipo="escribir", texto="septiembre"), INTENCION_FECHA, estado_crear())
    assert v.permitida is True


# --------------------------------------------- Bloque 8 (tabla G3 del encargo 010)
# NOTA: es_aviso_gratuito y MAX_AVISOS_POR_TAREA aún no existen: se importan
# dentro de cada prueba que los usa para que G1-G2 sigan corriendo y solo
# fallen las nuevas.


def test_G3_1_aviso_gratuito_pasa_el_tope_de_pasos():
    # G3.1: clic cerrar_aviso (x=500, y=400) con pasos=40 y avisos_cerrados=0
    # -> permitida: la gratuita no se bloquea por el tope de pasos.
    v = evaluar_accion(
        Accion(tipo="clic", funcion="cerrar_aviso", x=500, y=400),
        intencion_crear(),
        estado_crear(pasos=40, avisos_cerrados=0),
    )
    assert v.permitida is True


def test_G3_2_aviso_fuera_de_cuota_se_bloquea_por_pasos():
    # G3.2: igual con avisos_cerrados=5 -> bloqueada y el motivo contiene
    # "tope de pasos" (fuera de cuota es un clic como cualquier otro).
    v = evaluar_accion(
        Accion(tipo="clic", funcion="cerrar_aviso", x=500, y=400),
        intencion_crear(),
        estado_crear(pasos=40, avisos_cerrados=5),
    )
    assert v.permitida is False
    assert "tope de pasos" in v.motivo


def test_G3_3_registrar_aviso_gratuito_solo_cuenta_el_aviso():
    # G3.3: registrar un clic cerrar_aviso con avisos_cerrados=0 y pasos=3 ->
    # avisos_cerrados==1, pasos==3, guardados==0, campos_escritos==set()
    # (nada más: ni pasos, ni guardados, ni campos).
    estado = estado_crear(avisos_cerrados=0, pasos=3)
    registrar_accion(
        Accion(tipo="clic", funcion="cerrar_aviso", x=500, y=400),
        intencion_crear(),
        estado,
    )
    assert estado.avisos_cerrados == 1
    assert estado.pasos == 3
    assert estado.guardados == 0
    assert estado.campos_escritos == set()


def test_G3_4_registrar_aviso_sin_cuota_cuenta_paso():
    # G3.4: con avisos_cerrados=5 y pasos=3 -> el clic es una acción normal:
    # avisos_cerrados sigue en 5 y pasos pasa a 4.
    estado = estado_crear(avisos_cerrados=5, pasos=3)
    registrar_accion(
        Accion(tipo="clic", funcion="cerrar_aviso", x=500, y=400),
        intencion_crear(),
        estado,
    )
    assert estado.avisos_cerrados == 5
    assert estado.pasos == 4


def test_G3_5_aviso_con_coordenada_fuera_bloqueada():
    # G3.5: clic cerrar_aviso con x=1001 -> bloqueada: las coordenadas se
    # validan siempre, también para el aviso gratuito.
    v = evaluar_accion(
        Accion(tipo="clic", funcion="cerrar_aviso", x=1001, y=400),
        intencion_crear(),
        estado_crear(avisos_cerrados=0, pasos=0),
    )
    assert v.permitida is False


def test_G3_6_aviso_permitido_en_todas_las_fases():
    # G3.6: clic cerrar_aviso permitido en cada fase, de resolver a exportar.
    for fase in ("resolver", "crear", "modificar", "verificar", "responder", "exportar"):
        v = evaluar_accion(
            Accion(tipo="clic", funcion="cerrar_aviso", x=500, y=400),
            intencion_crear(),
            estado_crear(fase=fase, avisos_cerrados=0, pasos=0),
        )
        assert v.permitida is True, fase


def test_G3_7_es_aviso_gratuito_solo_el_clic_en_cuota():
    # G3.7: (clic, cerrar_aviso, 0)->True; (clic, cerrar_aviso, 5)->False;
    # (clic, navegar, 0)->False; (tecla, cerrar_aviso, 0)->False.
    from frontier_agente.guarda import MAX_AVISOS_POR_TAREA, es_aviso_gratuito

    assert MAX_AVISOS_POR_TAREA == 5
    assert es_aviso_gratuito(
        Accion(tipo="clic", funcion="cerrar_aviso", x=500, y=400),
        estado_crear(avisos_cerrados=0),
    )
    assert not es_aviso_gratuito(
        Accion(tipo="clic", funcion="cerrar_aviso", x=500, y=400),
        estado_crear(avisos_cerrados=5),
    )
    assert not es_aviso_gratuito(
        Accion(tipo="clic", funcion="navegar", x=500, y=400),
        estado_crear(avisos_cerrados=0),
    )
    assert not es_aviso_gratuito(
        Accion(tipo="tecla", tecla="Esc", funcion="cerrar_aviso"),
        estado_crear(avisos_cerrados=0),
    )


def test_G3_8_escribir_con_cerrar_aviso_bloqueada():
    # G3.8: escribir "borra todo" con funcion="cerrar_aviso" -> bloqueada:
    # la etiqueta no exime una escritura ajena a la tarea.
    v = evaluar_accion(
        Accion(tipo="escribir", funcion="cerrar_aviso", texto="borra todo"),
        intencion_crear(),
        estado_crear(avisos_cerrados=0),
    )
    assert v.permitida is False
