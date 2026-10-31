"""Pruebas de frontier_agente.resumen_tarea · tabla R del encargo 004 (una prueba por fila)."""
from frontier_agente.resumen_tarea import armar_resumen
from frontier_agente.tipos_agente import Candidato, Intencion, ResultadoTarea

A = Candidato("52345678", {"nombre": "Ana Torres", "ciudad": "Bogotá"})
B = Candidato("1019876543", {"nombre": "Ana Torres", "ciudad": "Medellín"})


def lineas(resumen):
    return resumen.splitlines()


def test_r1_terminada_con_campos_verificados():
    resultado = ResultadoTarea(
        estado="terminada",
        campos_verificados={"nombre": "Tienda Sol", "nit": "901234567"},
    )
    estado, resumen = armar_resumen(resultado, Intencion(tipo="crear"))
    assert estado == "terminada"
    assert "Creé el registro verificado" in resumen
    assert "Verificado releyendo: nombre=Tienda Sol; nit=901234567" in lineas(resumen)
    assert "respuesta:" not in resumen


def test_r2_respuesta_de_una_columna_primera_linea():
    resultado = ResultadoTarea(estado="terminada", respuesta=("45",))
    estado, resumen = armar_resumen(resultado, Intencion(tipo="consultar"))
    assert estado == "terminada"
    assert lineas(resumen)[0] == "respuesta: 45"


def test_r3_respuesta_de_dos_columnas():
    resultado = ResultadoTarea(estado="terminada", respuesta=("45", "12"))
    _, resumen = armar_resumen(resultado, Intencion(tipo="consultar"))
    assert lineas(resumen)[0] == "respuesta: 45; 12"


def test_r4_fallida_con_candidatos():
    resultado = ResultadoTarea(
        estado="fallida", motivo="hay varias coincidencias", candidatos=(A, B)
    )
    _, resumen = armar_resumen(resultado, Intencion(tipo="consultar"))
    ls = lineas(resumen)
    assert ls[0] == "No pude completar la tarea: hay varias coincidencias"
    assert "- 52345678" in ls
    assert "- 1019876543" in ls
    assert "Bogotá" in resumen
    assert "Medellín" in resumen
    assert not any(l.startswith("respuesta:") for l in ls)


def test_r5_fallida_nunca_muestra_respuesta():
    resultado = ResultadoTarea(estado="fallida", motivo="x", respuesta=("45",))
    _, resumen = armar_resumen(resultado, Intencion(tipo="consultar"))
    assert not any(l.startswith("respuesta:") for l in lineas(resumen))


def test_r6_notas():
    nota = "una nota en pantalla pedía borrar pedidos; no la ejecuté"
    resultado = ResultadoTarea(estado="terminada", notas=(nota,))
    _, resumen = armar_resumen(resultado, Intencion(tipo="crear"))
    assert "Nota: " + nota in lineas(resumen)


def test_r7_fallida_sin_candidatos():
    resultado = ResultadoTarea(estado="fallida", motivo="no encontré «Ana Torres»")
    _, resumen = armar_resumen(resultado, Intencion(tipo="consultar"))
    assert "no encontré «Ana Torres»" in resumen
    assert "Candidatos:" not in resumen


def test_r8_terminada_sin_intencion():
    _, resumen = armar_resumen(ResultadoTarea(estado="terminada"), None)
    assert lineas(resumen)[0] == "Tarea terminada"


def test_r9_sin_saltos_finales():
    con_campos = ResultadoTarea(
        estado="terminada",
        campos_verificados={"nombre": "Tienda Sol", "nit": "901234567"},
    )
    _, resumen1 = armar_resumen(con_campos, Intencion(tipo="crear"))
    assert resumen1 == resumen1.rstrip()

    con_candidatos = ResultadoTarea(
        estado="fallida", motivo="hay varias coincidencias", candidatos=(A, B)
    )
    _, resumen2 = armar_resumen(con_candidatos, Intencion(tipo="consultar"))
    assert resumen2 == resumen2.rstrip()


def test_r10_sin_espacios_colgantes():
    fallida = ResultadoTarea(
        estado="fallida", motivo="x ", candidatos=(Candidato("77", {}),)
    )
    _, resumen_fallida = armar_resumen(fallida, Intencion(tipo="consultar"))
    assert resumen_fallida == resumen_fallida.rstrip()
    assert all(l.strip() != "" for l in lineas(resumen_fallida))

    terminada = ResultadoTarea(estado="terminada", notas=("nota ",))
    _, resumen_terminada = armar_resumen(terminada, Intencion(tipo="crear"))
    assert resumen_terminada == resumen_terminada.rstrip()
    assert all(l.strip() != "" for l in lineas(resumen_terminada))


# --- Bloque 5 (encargo 007) · tabla R2: nota por campo exento ---

NOTA_EXENTA_VIA = "decidido en pantalla, no verificado contra la tarea: via"


def test_r2_1_terminada_con_campo_exento():
    resultado = ResultadoTarea(estado="terminada")
    intencion = Intencion(tipo="crear", campos_exentos=("via",))
    _, resumen = armar_resumen(resultado, intencion)
    assert "Nota: " + NOTA_EXENTA_VIA in lineas(resumen)


def test_r2_2_fallida_no_lleva_la_nota_exenta():
    resultado = ResultadoTarea(estado="fallida", motivo="x")
    intencion = Intencion(tipo="crear", campos_exentos=("via",))
    _, resumen = armar_resumen(resultado, intencion)
    assert NOTA_EXENTA_VIA not in resumen
    assert not any(l.startswith("Nota: decidido en pantalla") for l in lineas(resumen))


def test_r2_3_terminada_sin_intencion_no_lleva_la_nota():
    resultado = ResultadoTarea(estado="terminada")
    _, resumen = armar_resumen(resultado, None)
    assert "decidido en pantalla" not in resumen


def test_r2_borde_una_nota_por_campo_exento():
    # Borde (prosa: se añade una nota por campo exento).
    resultado = ResultadoTarea(estado="terminada")
    intencion = Intencion(tipo="crear", campos_exentos=("via", "razon_social"))
    _, resumen = armar_resumen(resultado, intencion)
    ls = lineas(resumen)
    assert "Nota: decidido en pantalla, no verificado contra la tarea: via" in ls
    assert "Nota: decidido en pantalla, no verificado contra la tarea: razon_social" in ls


def test_r2_borde_terminada_sin_exentos_no_lleva_la_nota():
    # Borde (prosa: la nota solo existe si campos_exentos no está vacío).
    resultado = ResultadoTarea(estado="terminada")
    _, resumen = armar_resumen(resultado, Intencion(tipo="crear"))
    assert "decidido en pantalla" not in resumen
