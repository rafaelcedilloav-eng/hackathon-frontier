"""
Pruebas del esqueleto HTTP del contrato (Tabla H, encargo 002).

Cada fila de la Tabla H es una prueba (H1-H23). Se corre con
`cd agente && python -m pytest` (sin conftest.py: esa invocación ya pone
`agente/` en `sys.path`). No hay pytest-asyncio: cada escenario corre
dentro de `asyncio.run(...)` con `httpx.ASGITransport`.
"""
import ast
import asyncio
import gc
import logging
import time
from pathlib import Path

import httpx
import pytest
from frontier_agente.errores import ErrorConfiguracion
from frontier_agente.servidor import crear_app
from frontier_agente.tipos import Escritorio

# NOTA: constantes de la tabla H (fila de encabezado).
TOKEN = "tok-prueba-123"
PASSWORD = "Zeta-9981-Prueba"
URL_MESA1 = "wss://mesa1.ejemplo.com/websockify"
URL_MESA1_MAYUS = "WSS://MESA1.ejemplo.com/websockify/"
URL_MESA2 = "wss://mesa2.ejemplo.com/websockify"
CABECERA_TOKEN = {"Authorization": f"Bearer {TOKEN}"}


def _cuerpo(tarea="revisar", url=URL_MESA1, password=PASSWORD):
    """Cuerpo válido de POST /tasks (punto 3 del contrato)."""
    return {"tarea": tarea, "escritorio": {"url": url, "password": password}}


def _cliente(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba")


def _ejecutor_ok():
    """Ejecutor falso instantáneo que termina bien."""

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        return ("terminada", "hecho")

    return ejecutar


async def _esperar_estado(cliente, task_id, estados, margen_s=2.0):
    """GET /tasks/{id} hasta alcanzar uno de `estados` (o agotar el margen)."""
    if isinstance(estados, str):
        estados = (estados,)
    fin = time.perf_counter() + margen_s
    respuesta = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
    while respuesta.json().get("estado") not in estados and time.perf_counter() < fin:
        await asyncio.sleep(0.05)
        respuesta = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
    return respuesta


# ---------------------------------------------------------------------------
# H1 · GET /health sin cabecera y con token -> 200 {"ok": true}
# ---------------------------------------------------------------------------
def test_H01_health_con_y_sin_token():
    app = crear_app(ejecutar=_ejecutor_ok(), token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            sin = await cliente.get("/health")
            con = await cliente.get("/health", headers=CABECERA_TOKEN)
        return sin, con

    sin, con = asyncio.run(esc())
    assert sin.status_code == 200
    assert sin.json() == {"ok": True}
    assert con.status_code == 200
    assert con.json() == {"ok": True}


# ---------------------------------------------------------------------------
# H2 · POST /tasks con tres autorizaciones inválidas -> 401, sin ejecutar nada
# ---------------------------------------------------------------------------
def test_H02_post_sin_autorizacion_adecuada():
    llamadas = []

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        llamadas.append(tarea)
        return ("terminada", "hecho")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            sin = await cliente.post("/tasks", json=_cuerpo())
            esquema = await cliente.post(
                "/tasks", json=_cuerpo(), headers={"Authorization": f"Token {TOKEN}"}
            )
            otro = await cliente.post(
                "/tasks", json=_cuerpo(), headers={"Authorization": "Bearer otro"}
            )
        return sin, esquema, otro

    sin, esquema, otro = asyncio.run(esc())
    assert sin.status_code == 401
    assert esquema.status_code == 401
    assert otro.status_code == 401
    assert llamadas == []


# ---------------------------------------------------------------------------
# H3 · POST válido no espera al ejecutor; en_curso y luego terminada
# ---------------------------------------------------------------------------
def test_H03_post_no_espera_al_ejecutor():
    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        await asyncio.sleep(0.3)
        return ("terminada", "hecho")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            t0 = time.perf_counter()
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            demora = time.perf_counter() - t0
            cuerpo = r.json()
            task_id = cuerpo["task_id"]
            inmediato = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
            await asyncio.sleep(0.6)
            despues = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
        return r.status_code, demora, cuerpo, inmediato, despues

    estado, demora, cuerpo, inmediato, despues = asyncio.run(esc())
    assert estado == 200
    assert demora < 0.5
    assert list(cuerpo.keys()) == ["task_id"]
    assert isinstance(cuerpo["task_id"], str) and cuerpo["task_id"]
    assert inmediato.json() == {"estado": "en_curso", "resumen": ""}
    assert despues.json() == {"estado": "terminada", "resumen": "hecho"}


# ---------------------------------------------------------------------------
# H4 · POST con cuatro cuerpos inválidos -> 422, sin ejecutar nada
# ---------------------------------------------------------------------------
def test_H04_post_cuerpos_invalidos():
    llamadas = []

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        llamadas.append(tarea)
        return ("terminada", "hecho")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            sin_tarea = await cliente.post(
                "/tasks",
                json={"escritorio": {"url": URL_MESA1, "password": PASSWORD}},
                headers=CABECERA_TOKEN,
            )
            tarea_vacia = await cliente.post(
                "/tasks", json=_cuerpo(tarea=""), headers=CABECERA_TOKEN
            )
            sin_password = await cliente.post(
                "/tasks",
                json={"tarea": "x", "escritorio": {"url": URL_MESA1}},
                headers=CABECERA_TOKEN,
            )
            no_json = await cliente.post(
                "/tasks",
                content="no-es-json",
                headers={**CABECERA_TOKEN, "Content-Type": "text/plain"},
            )
        return [sin_tarea, tarea_vacia, sin_password, no_json]

    respuestas = asyncio.run(esc())
    assert [r.status_code for r in respuestas] == [422, 422, 422, 422]
    assert llamadas == []


# ---------------------------------------------------------------------------
# H5 · GET /tasks/{id}: id desconocido con token -> 404; id válido sin token -> 401
# ---------------------------------------------------------------------------
def test_H05_404_y_401_en_tasks_id():
    app = crear_app(ejecutar=_ejecutor_ok(), token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            desconocido = await cliente.get("/tasks/no-existe", headers=CABECERA_TOKEN)
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            task_id = r.json()["task_id"]
            sin_token = await cliente.get(f"/tasks/{task_id}")
        return desconocido, sin_token

    desconocido, sin_token = asyncio.run(esc())
    assert desconocido.status_code == 404
    assert sin_token.status_code == 401


# ---------------------------------------------------------------------------
# H6 · Ejecutor que devuelve ("fallida", "motivo X")
# ---------------------------------------------------------------------------
def test_H06_ejecutor_devuelve_fallida():
    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        return ("fallida", "motivo X")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            return await _esperar_estado(cliente, r.json()["task_id"], "fallida")

    assert asyncio.run(esc()).json() == {"estado": "fallida", "resumen": "motivo X"}


# ---------------------------------------------------------------------------
# H7 · Excepción del ejecutor: nombre de la clase sí, texto y "clave" no
# ---------------------------------------------------------------------------
def test_H07_excepcion_del_ejecutor_sin_secretos():
    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        raise RuntimeError("clave Zeta-9981-Prueba")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            return await _esperar_estado(cliente, r.json()["task_id"], "fallida")

    cuerpo = asyncio.run(esc()).json()
    assert cuerpo["estado"] == "fallida"
    assert "RuntimeError" in cuerpo["resumen"]
    assert "Zeta-9981-Prueba" not in cuerpo["resumen"]
    assert "clave" not in cuerpo["resumen"]


# ---------------------------------------------------------------------------
# H8 · Resultados inválidos del ejecutor -> "Resultado inválido del ejecutor"
# ---------------------------------------------------------------------------
def test_H08_resultado_invalido_del_ejecutor():
    invalidos = [("quizas", "x"), "hola"]

    async def ejecutar(tarea: str, escritorio: Escritorio):
        return invalidos[int(tarea)]

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        respuestas = []
        async with _cliente(app) as cliente:
            for i in range(len(invalidos)):
                cuerpo = _cuerpo(tarea=str(i), url=f"wss://mesa{i}.ejemplo.com/websockify")
                r = await cliente.post("/tasks", json=cuerpo, headers=CABECERA_TOKEN)
                respuestas.append(await _esperar_estado(cliente, r.json()["task_id"], "fallida"))
        return respuestas

    for respuesta in asyncio.run(esc()):
        assert respuesta.json() == {"estado": "fallida", "resumen": "Resultado inválido del ejecutor"}


# ---------------------------------------------------------------------------
# H9 · Vigilante: tope 0.5 s, cancelación que llega al ejecutor
# ---------------------------------------------------------------------------
def test_H09_vigilante_cancela_al_tope():
    bandera = {"cancelado": False}

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        try:
            await asyncio.sleep(30)
        finally:
            bandera["cancelado"] = True

    app = crear_app(ejecutar=ejecutar, token=TOKEN, tope_tarea_s=0.5)

    async def esc():
        async with _cliente(app) as cliente:
            t0 = time.perf_counter()
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            task_id = r.json()["task_id"]
            await asyncio.sleep(0.25)  # antes del tope de 0.5 s
            antes = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
            assert antes.json()["estado"] == "en_curso"
            g = antes
            while time.perf_counter() - t0 < 1.5:
                g = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
                if g.json()["estado"] == "fallida":
                    return g
                await asyncio.sleep(0.05)
            return g

    cuerpo = asyncio.run(esc()).json()
    assert cuerpo["estado"] == "fallida"
    assert "Tiempo agotado" in cuerpo["resumen"]
    assert bandera["cancelado"] is True


# ---------------------------------------------------------------------------
# H10 · Resumen depurado: password del escritorio y token -> [oculto]
# ---------------------------------------------------------------------------
def test_H10_resumen_depurado_con_password_y_token():
    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        return ("terminada", f"listo con {PASSWORD} y {TOKEN}")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            return await _esperar_estado(cliente, r.json()["task_id"], "terminada")

    esperado = {"estado": "terminada", "resumen": "listo con [oculto] y [oculto]"}
    assert asyncio.run(esc()).json() == esperado


# ---------------------------------------------------------------------------
# H11 / H12 · Candado por escritorio: la tarea nueva reemplaza a la anterior
# (H12 usa la url en mayúsculas con barra final: es el mismo escritorio)
# ---------------------------------------------------------------------------
async def _escenario_reemplazo(url_segunda):
    eventos = []

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        if escritorio.password == PASSWORD:
            eventos.append("inicio1")
            try:
                await asyncio.sleep(30)
            finally:
                eventos.append("cancelado1")
        else:
            eventos.append("inicio2")
            return ("terminada", "tarea 2 lista")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)
    async with _cliente(app) as cliente:
        r1 = await cliente.post(
            "/tasks", json=_cuerpo(tarea="tarea1"), headers=CABECERA_TOKEN
        )
        assert r1.status_code == 200
        id1 = r1.json()["task_id"]
        await asyncio.sleep(0.1)  # deja arrancar al ejecutor 1
        t0 = time.perf_counter()
        r2 = await cliente.post(
            "/tasks",
            json=_cuerpo(tarea="tarea2", url=url_segunda, password="Otra-Clave-77"),
            headers=CABECERA_TOKEN,
        )
        assert r2.status_code == 200
        assert time.perf_counter() - t0 < 0.5
        id2 = r2.json()["task_id"]
        for _ in range(100):
            if len(eventos) >= 3:
                break
            await asyncio.sleep(0.05)
        assert eventos == ["inicio1", "cancelado1", "inicio2"]
        g1 = await _esperar_estado(cliente, id1, "fallida")
        g2 = await _esperar_estado(cliente, id2, "terminada")
        return g1.json(), g2.json()


def test_H11_reemplazo_en_el_mismo_escritorio():
    tarea1, tarea2 = asyncio.run(_escenario_reemplazo(URL_MESA1))
    assert tarea1 == {"estado": "fallida", "resumen": "Reemplazada por una tarea nueva en el mismo escritorio"}
    assert tarea2 == {"estado": "terminada", "resumen": "tarea 2 lista"}


def test_H12_mismo_escritorio_con_url_en_mayusculas():
    tarea1, tarea2 = asyncio.run(_escenario_reemplazo(URL_MESA1_MAYUS))
    assert tarea1 == {"estado": "fallida", "resumen": "Reemplazada por una tarea nueva en el mismo escritorio"}
    assert tarea2 == {"estado": "terminada", "resumen": "tarea 2 lista"}


# ---------------------------------------------------------------------------
# H13 · Escritorios distintos corren en paralelo
# ---------------------------------------------------------------------------
def test_H13_escritorios_distintos_en_paralelo():
    eventos = []

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        eventos.append(("inicio", escritorio.url))
        await asyncio.sleep(0.3)
        eventos.append(("fin", escritorio.url))
        return ("terminada", "hecho")

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            await cliente.post(
                "/tasks", json=_cuerpo(url=URL_MESA1), headers=CABECERA_TOKEN
            )
            await cliente.post(
                "/tasks", json=_cuerpo(url=URL_MESA2), headers=CABECERA_TOKEN
            )
            for _ in range(100):
                if len(eventos) >= 4:
                    break
                await asyncio.sleep(0.05)

    asyncio.run(esc())
    indices_inicio = [i for i, e in enumerate(eventos) if e[0] == "inicio"]
    indices_fin = [i for i, e in enumerate(eventos) if e[0] == "fin"]
    assert len(indices_inicio) == 2 and len(indices_fin) == 2
    assert max(indices_inicio) < min(indices_fin)  # ambos empiezan antes de que alguno termine


# ---------------------------------------------------------------------------
# H14 · caplog en DEBUG durante H3, H7 y H10: ningún secreto en los logs
# ---------------------------------------------------------------------------
def test_H14_ningun_secreto_en_los_logs(caplog):
    caplog.set_level(logging.DEBUG)

    async def ejecutor_h3(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        await asyncio.sleep(0.05)
        return ("terminada", "hecho")

    async def ejecutor_h7(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        raise RuntimeError(f"clave {PASSWORD}")

    async def ejecutor_h10(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        return ("terminada", f"listo con {PASSWORD} y {TOKEN}")

    async def esc():
        for ejecutor in (ejecutor_h3, ejecutor_h7, ejecutor_h10):
            app = crear_app(ejecutar=ejecutor, token=TOKEN)
            async with _cliente(app) as cliente:
                r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
                await _esperar_estado(cliente, r.json()["task_id"], ("terminada", "fallida"))

    asyncio.run(esc())
    texto = caplog.text
    assert PASSWORD not in texto
    assert TOKEN not in texto


# ---------------------------------------------------------------------------
# H15 · Token por FRONTIER_TEAM_TOKEN; sin token ni variable -> ErrorConfiguracion
# ---------------------------------------------------------------------------
def test_H15_token_por_variable_de_entorno(monkeypatch):
    monkeypatch.delenv("FRONTIER_TEAM_TOKEN", raising=False)
    with pytest.raises(ErrorConfiguracion) as info:
        crear_app()
    assert "FRONTIER_TEAM_TOKEN" in str(info.value)

    monkeypatch.setenv("FRONTIER_TEAM_TOKEN", TOKEN)
    app = crear_app()

    async def esc():
        async with _cliente(app) as cliente:
            return await cliente.get("/health")

    respuesta = asyncio.run(esc())
    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}


# ---------------------------------------------------------------------------
# H16 · Registro de 200 tareas: la 201 desaloja a la más antigua
# ---------------------------------------------------------------------------
def test_H16_registro_descarta_la_mas_antigua():
    app = crear_app(ejecutar=_ejecutor_ok(), token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            ids = []
            for i in range(201):
                cuerpo = _cuerpo(tarea=f"tarea {i}", url=f"wss://mesa{i}.ejemplo.com/websockify")
                r = await cliente.post("/tasks", json=cuerpo, headers=CABECERA_TOKEN)
                assert r.status_code == 200
                ids.append(r.json()["task_id"])
            primera = await cliente.get(f"/tasks/{ids[0]}", headers=CABECERA_TOKEN)
            ultima = await cliente.get(f"/tasks/{ids[-1]}", headers=CABECERA_TOKEN)
        return primera, ultima

    primera, ultima = asyncio.run(esc())
    assert primera.status_code == 404
    assert ultima.status_code == 200


# ---------------------------------------------------------------------------
# H17 · Sin ejecutor: ejecutor por defecto -> fallida inmediata
# ---------------------------------------------------------------------------
def test_H17_ejecutor_por_defecto_sin_configurar():
    app = crear_app(token=TOKEN)  # sin argumento ejecutor -> ejecutor por defecto (punto 5)

    async def esc():
        async with _cliente(app) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            assert r.status_code == 200
            task_id = r.json()["task_id"]
            await asyncio.sleep(0.2)
            return await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)

    esperado = {"estado": "fallida", "resumen": "Agente sin ejecutor configurado"}
    assert asyncio.run(esc()).json() == esperado


# ---------------------------------------------------------------------------
# H18 · Higiene: sin __check/__reset/print( en frontier_agente/; Procfile correcto
# ---------------------------------------------------------------------------
def test_H18_higiene_del_paquete():
    carpeta = Path(__file__).resolve().parents[1] / "frontier_agente"
    archivos = sorted(carpeta.glob("*.py"))
    assert archivos, "debería existir agente/frontier_agente/ con archivos .py"
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        assert "__check" not in texto, archivo.name
        assert "__reset" not in texto, archivo.name
        assert "print(" not in texto, archivo.name
    procfile = carpeta.parent / "Procfile"
    assert procfile.is_file(), "debería existir agente/Procfile"
    assert "web: python -m frontier_agente" in procfile.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# H19 · Tres POST seguidos al mismo escritorio: nunca dos ejecutores vivos
# ---------------------------------------------------------------------------
def test_H19_tres_post_seguidos_al_mismo_escritorio():
    vivos = {"ahora": 0, "maximo": 0}

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        vivos["ahora"] += 1
        vivos["maximo"] = max(vivos["maximo"], vivos["ahora"])
        try:
            if tarea == "tarea3":
                return ("terminada", "la 3 lista")
            await asyncio.sleep(30)
        finally:
            vivos["ahora"] -= 1

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            ids = []
            for i in (1, 2, 3):
                r = await cliente.post(
                    "/tasks", json=_cuerpo(tarea=f"tarea{i}"), headers=CABECERA_TOKEN
                )
                assert r.status_code == 200
                ids.append(r.json()["task_id"])
            g1 = await _esperar_estado(cliente, ids[0], "fallida", margen_s=8.0)
            g2 = await _esperar_estado(cliente, ids[1], "fallida", margen_s=8.0)
            g3 = await _esperar_estado(cliente, ids[2], "terminada", margen_s=8.0)
        return g1.json(), g2.json(), g3.json()

    tarea1, tarea2, tarea3 = asyncio.run(esc())
    reemplazada = {"estado": "fallida", "resumen": "Reemplazada por una tarea nueva en el mismo escritorio"}
    assert tarea1 == reemplazada
    assert tarea2 == reemplazada
    assert tarea3 == {"estado": "terminada", "resumen": "la 3 lista"}
    assert vivos["maximo"] == 1  # nunca hubo dos ejecutores vivos a la vez


# ---------------------------------------------------------------------------
# H20 · Resultado tardío tras una cancelación se descarta (nunca "tarde")
# ---------------------------------------------------------------------------
def test_H20_resultado_tardio_se_descarta():
    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        if tarea == "rapida":
            return ("terminada", "ok tarea 2")
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return ("terminada", "tarde")  # resultado tardío: debe descartarse

    # (a) tope de 0.5 s: queda fallida con Tiempo agotado, no "tarde"
    app_a = crear_app(ejecutar=ejecutar, token=TOKEN, tope_tarea_s=0.5)

    async def esc_a():
        async with _cliente(app_a) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            return await _esperar_estado(cliente, r.json()["task_id"], "fallida")

    cuerpo_a = asyncio.run(esc_a()).json()
    assert cuerpo_a["estado"] == "fallida"
    assert "Tiempo agotado" in cuerpo_a["resumen"]
    assert cuerpo_a["resumen"] != "tarde"

    # (b) reemplazo por otra tarea al mismo escritorio: Reemplazada..., no "tarde"
    app_b = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc_b():
        async with _cliente(app_b) as cliente:
            r1 = await cliente.post(
                "/tasks", json=_cuerpo(tarea="lenta"), headers=CABECERA_TOKEN
            )
            id1 = r1.json()["task_id"]
            await asyncio.sleep(0.1)  # deja arrancar al ejecutor lento
            r2 = await cliente.post(
                "/tasks", json=_cuerpo(tarea="rapida"), headers=CABECERA_TOKEN
            )
            id2 = r2.json()["task_id"]
            g2 = await _esperar_estado(cliente, id2, "terminada")
            await asyncio.sleep(0.3)  # margen: si el resultado tardío se guardara, ya cayó
            g1 = await cliente.get(f"/tasks/{id1}", headers=CABECERA_TOKEN)
        return g1.json(), g2.json()

    cuerpo_b1, cuerpo_b2 = asyncio.run(esc_b())
    assert cuerpo_b1 == {"estado": "fallida", "resumen": "Reemplazada por una tarea nueva en el mismo escritorio"}
    assert cuerpo_b1["resumen"] != "tarde"
    assert cuerpo_b2 == {"estado": "terminada", "resumen": "ok tarea 2"}


# ---------------------------------------------------------------------------
# H21 · Ejecutor que ignora la cancelación: fallida igualmente y el servicio sigue
# ---------------------------------------------------------------------------
def test_H21_ejecutor_que_ignora_la_cancelacion():
    parar = {"v": False}

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        while not parar["v"]:  # atrapa CancelledError en bucle y sigue
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                continue
        return ("fallida", "detenida por la prueba")

    app = crear_app(
        ejecutar=ejecutar, token=TOKEN, tope_tarea_s=0.3, espera_cancelacion_s=0.3
    )

    async def esc():
        async with _cliente(app) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            assert r.status_code == 200
            task_id = r.json()["task_id"]
            t0 = time.perf_counter()
            g = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
            while g.json()["estado"] != "fallida" and time.perf_counter() - t0 < 1.5:
                await asyncio.sleep(0.05)
                g = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
            salud = await cliente.get("/health")
            parar["v"] = True  # la prueba detiene al ejecutor
        return g.json(), salud

    cuerpo, salud = asyncio.run(esc())
    assert cuerpo["estado"] == "fallida"
    assert "Tiempo agotado" in cuerpo["resumen"]
    assert salud.status_code == 200
    assert salud.json() == {"ok": True}


# ---------------------------------------------------------------------------
# H22 · La contraseña no sale en el repr de Escritorio ni en el texto del 422
# ---------------------------------------------------------------------------
def test_H22_password_fuera_de_repr_y_de_la_respuesta_422():
    assert PASSWORD not in repr(Escritorio("wss://x", PASSWORD))

    app = crear_app(ejecutar=_ejecutor_ok(), token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            r = await cliente.post(
                "/tasks",
                json={"escritorio": {"url": URL_MESA1, "password": PASSWORD}},  # sin tarea
                headers=CABECERA_TOKEN,
            )
        return r.status_code, r.text

    estado, texto = asyncio.run(esc())
    assert estado == 422
    assert PASSWORD not in texto


# ---------------------------------------------------------------------------
# H23 · Higiene (ast): # NOTA: en las líneas PROPIAS de cada función
# (una función con internas no se salva por la nota de una interna; punto 14)
# ---------------------------------------------------------------------------
def _funciones_sin_nota_propia(texto: str, arbol: ast.Module, ruta: str) -> list[str]:
    """Funciones sin `# NOTA:` en sus propias líneas, sin contar las de sus internas."""
    lineas = texto.splitlines()
    faltantes = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cubiertas: set[int] = set()
        for interna in ast.walk(nodo):
            if interna is nodo:
                continue
            if isinstance(interna, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cubiertas.update(range(interna.lineno, interna.end_lineno + 1))
        propias = [
            lineas[n - 1]
            for n in range(nodo.lineno, nodo.end_lineno + 1)
            if n not in cubiertas
        ]
        if not any("# NOTA:" in linea for linea in propias):
            faltantes.append(f"{ruta}:{nodo.name}")
    return faltantes


def test_H23_nota_en_cada_funcion():
    base = Path(__file__).resolve().parents[1]
    faltantes = []
    for paquete in ("frontier_agente", "arnes"):
        for archivo in sorted((base / paquete).glob("*.py")):
            texto = archivo.read_text(encoding="utf-8")
            arbol = ast.parse(texto)  # si no parsea, la prueba falla aquí con el SyntaxError
            faltantes.extend(
                _funciones_sin_nota_propia(texto, arbol, f"{paquete}/{archivo.name}")
            )
    assert not faltantes, "funciones sin # NOTA: en sus propias líneas: " + ", ".join(faltantes)


# ---------------------------------------------------------------------------
# H24 · Tres POST al mismo escritorio con cierre lento del ejecutor 1:
# nunca dos ejecutores vivos, tampoco mientras el anterior tarda en cerrarse
# ---------------------------------------------------------------------------
def test_H24_cierre_lento_del_anterior():
    vivos = {"ahora": 0, "maximo": 0}

    async def ejecutar(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        vivos["ahora"] += 1
        vivos["maximo"] = max(vivos["maximo"], vivos["ahora"])
        try:
            if tarea == "tarea3":
                return ("terminada", "la 3 lista")
            await asyncio.sleep(30)
        finally:
            if tarea == "tarea1":
                await asyncio.sleep(0.5)  # tarda en cerrarse (cumple la cancelación)
            vivos["ahora"] -= 1

    app = crear_app(ejecutar=ejecutar, token=TOKEN)

    async def esc():
        async with _cliente(app) as cliente:
            ids = []
            for i in (1, 2, 3):
                r = await cliente.post(
                    "/tasks", json=_cuerpo(tarea=f"tarea{i}"), headers=CABECERA_TOKEN
                )
                assert r.status_code == 200
                ids.append(r.json()["task_id"])
            g1 = await _esperar_estado(cliente, ids[0], "fallida", margen_s=8.0)
            g2 = await _esperar_estado(cliente, ids[1], "fallida", margen_s=8.0)
            g3 = await _esperar_estado(cliente, ids[2], "terminada", margen_s=8.0)
        return g1.json(), g2.json(), g3.json()

    tarea1, tarea2, tarea3 = asyncio.run(esc())
    reemplazada = {"estado": "fallida", "resumen": "Reemplazada por una tarea nueva en el mismo escritorio"}
    assert tarea1 == reemplazada
    assert tarea2 == reemplazada
    assert tarea3 == {"estado": "terminada", "resumen": "la 3 lista"}
    assert vivos["maximo"] == 1  # tampoco mientras el ejecutor 1 tardó en cerrarse


# ---------------------------------------------------------------------------
# H25 · Excepciones del ejecutor (corrutina o no) nunca en logs, ni siquiera
# la que ocurre después de cancelado (ni «Task exception was never retrieved»)
# ---------------------------------------------------------------------------
def test_H25_excepciones_del_ejecutor_nunca_en_logs(caplog):
    caplog.set_level(logging.DEBUG)

    # (a) «ejecutor» que no es corrutina: función normal que lanza antes de empezar
    def ejecutar_sync(tarea: str, escritorio: Escritorio):
        raise RuntimeError(f"clave {PASSWORD}")

    app_a = crear_app(ejecutar=ejecutar_sync, token=TOKEN)

    async def esc_a():
        async with _cliente(app_a) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            assert r.status_code == 200
            return await _esperar_estado(cliente, r.json()["task_id"], "fallida")

    cuerpo_a = asyncio.run(esc_a()).json()
    assert cuerpo_a["estado"] == "fallida"
    assert "RuntimeError" in cuerpo_a["resumen"]
    assert PASSWORD not in cuerpo_a["resumen"]

    # (b) ejecutor que ignora la cancelación y, pasados 0.6 s, lanza con un secreto
    async def ejecutar_tardio(tarea: str, escritorio: Escritorio) -> tuple[str, str]:
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 0.6:
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                continue  # ignora la cancelación
        raise RuntimeError(f"clave {PASSWORD}")

    app_b = crear_app(
        ejecutar=ejecutar_tardio, token=TOKEN, tope_tarea_s=0.3, espera_cancelacion_s=0.3
    )

    async def esc_b():
        async with _cliente(app_b) as cliente:
            r = await cliente.post("/tasks", json=_cuerpo(), headers=CABECERA_TOKEN)
            assert r.status_code == 200
            task_id = r.json()["task_id"]
            t0 = time.perf_counter()
            g = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
            while g.json()["estado"] != "fallida" and time.perf_counter() - t0 < 1.5:
                await asyncio.sleep(0.05)
                g = await cliente.get(f"/tasks/{task_id}", headers=CABECERA_TOKEN)
            await asyncio.sleep(1.0)  # espera 1 s más: la excepción de las 0.6 s ya ocurrió
            return g.json()

    cuerpo_b = asyncio.run(esc_b())
    assert cuerpo_b["estado"] == "fallida"
    assert "Tiempo agotado" in cuerpo_b["resumen"]

    gc.collect()  # fuerza el recolector: una excepción sin recoger reclamaría aquí
    assert PASSWORD not in caplog.text
