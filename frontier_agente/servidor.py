"""Servicio HTTP del contrato: /health, POST /tasks y GET /tasks/{id} (Tabla H)."""
import hmac
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from frontier_agente.errores import ErrorConfiguracion
from frontier_agente.registro_tareas import (
    ESPERA_CANCELACION_S,
    TOPE_TAREA_S,
    Ejecutor,
    RegistroTareas,
)
from frontier_agente.tipos import Escritorio

# NOTA: variables de entorno del contrato (puntos 9 y 11); las llaves nunca van en el código.
NOMBRE_VARIABLE_TOKEN = "FRONTIER_TEAM_TOKEN"
NOMBRE_VARIABLE_OPENROUTER = "OPENROUTER_API_KEY"

# NOTA: textos fijos del HTTP; sin números mágicos en las rutas.
ESQUEMA_AUTORIZACION = "bearer"
DETALLE_NO_AUTORIZADO = "No autorizado"
DETALLE_NO_ENCONTRADO = "Tarea no encontrada"


class EscritorioEntrada(BaseModel):
    """Escritorio tal como llega en el cuerpo de POST /tasks; los campos extra se ignoran."""

    model_config = ConfigDict(extra="ignore")

    url: str = Field(min_length=1)
    # NOTA: repr=False para que la contraseña no salga en el repr del modelo (punto 13).
    password: str = Field(min_length=1, repr=False)


class TareaEntrada(BaseModel):
    """Cuerpo de POST /tasks (punto 3): tarea no vacía y escritorio; campos extra ignorados."""

    model_config = ConfigDict(extra="ignore")

    tarea: str = Field(min_length=1)
    escritorio: EscritorioEntrada


def _resolver_token(token: str | None) -> str:
    """Punto 11: argumento o FRONTIER_TEAM_TOKEN; sin ninguno, ErrorConfiguracion que la nombra."""
    # NOTA: el token es del entorno o del argumento; nunca un valor fijo en el código.
    resuelto = token or os.environ.get(NOMBRE_VARIABLE_TOKEN)
    if not resuelto:
        raise ErrorConfiguracion(
            f"Falta el token del equipo: define la variable {NOMBRE_VARIABLE_TOKEN}"
        )
    return resuelto


def _secretos_globales(token: str) -> list[str]:
    """Punto 9: el token del equipo y OPENROUTER_API_KEY si existe; la contraseña va por tarea."""
    # NOTA: la contraseña del escritorio no va aquí: se depura con la de cada tarea.
    secretos = [token]
    clave_openrouter = os.environ.get(NOMBRE_VARIABLE_OPENROUTER)
    if clave_openrouter:
        secretos.append(clave_openrouter)
    return secretos


def _crear_verificador(token: str) -> Callable[..., Awaitable[None]]:
    """Punto 1: dependencia que exige Authorization: Bearer <token> o responde 401 sin ejecutar nada."""
    # NOTA: factoría que captura el token; la nota de su interna no cuenta para esta (punto 14).
    async def verificar(
        autorizacion: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> None:
        # NOTA: comparación en tiempo constante (hmac); sin cabecera o con otro esquema, 401.
        esquema, _, valor = (autorizacion or "").partition(" ")
        coincide = (
            valor != ""
            and esquema.lower() == ESQUEMA_AUTORIZACION
            and hmac.compare_digest(valor.encode("utf-8"), token.encode("utf-8"))
        )
        if not coincide:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=DETALLE_NO_AUTORIZADO
            )

    return verificar


def _crear_lifespan(registro: RegistroTareas) -> Callable[[FastAPI], AsyncIterator[None]]:
    """Punto 12: al apagar la app se cancelan las tareas en curso."""
    # NOTA: factoría que captura el registro; su interna hace el cierre al terminar el lifespan.
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # NOTA: al cerrar la app se cancelan las tareas en curso (punto 12).
        yield
        await registro.apagar()

    return lifespan


async def _manejar_cuerpo_invalido(_: Request, error: RequestValidationError) -> JSONResponse:
    """Punto 3: cuerpo inválido responde 422 sin repetir el cuerpo de la petición."""
    # NOTA: solo loc/msg/type; el detalle de pydantic trae el valor de entrada (la contraseña).
    detalles = [
        {"loc": detalle.get("loc"), "msg": detalle.get("msg"), "type": detalle.get("type")}
        for detalle in error.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": detalles}
    )


def _registrar_rutas(
    app: FastAPI, registro: RegistroTareas, verificador: Callable[..., Awaitable[None]]
) -> None:
    """Las 3 rutas del contrato; POST y GET /tasks/{id} exigen token, /health no (punto 1)."""
    # NOTA: factoría de rutas; cada ruta interna lleva su propia nota (punto 14).
    autorizacion = Depends(verificador)

    @app.get("/health")
    async def saludar() -> dict[str, bool]:
        # NOTA: sin token: el health check de la plataforma no manda cabeceras.
        return {"ok": True}

    @app.post("/tasks", dependencies=[autorizacion])
    async def crear_tarea(cuerpo: TareaEntrada) -> dict[str, str]:
        # NOTA: no espera al ejecutor (punto 3): registra en_curso y responde ya el id.
        escritorio = Escritorio(url=cuerpo.escritorio.url, password=cuerpo.escritorio.password)
        return {"task_id": registro.crear_tarea(cuerpo.tarea, escritorio)}

    @app.get("/tasks/{task_id}", dependencies=[autorizacion])
    async def leer_tarea(task_id: str) -> dict[str, str]:
        # NOTA: id desconocido -> 404 (punto 4); el estado sale del registro compartido.
        hallado = registro.estado_de(task_id)
        if hallado is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=DETALLE_NO_ENCONTRADO
            )
        estado, resumen = hallado
        return {"estado": estado, "resumen": resumen}

    app.add_exception_handler(RequestValidationError, _manejar_cuerpo_invalido)


def crear_app(
    ejecutar: Ejecutor | None = None,
    *,
    token: str | None = None,
    tope_tarea_s: float = TOPE_TAREA_S,
    espera_cancelacion_s: float = ESPERA_CANCELACION_S,
) -> FastAPI:
    """Arma la app del contrato: valida el token (punto 11) y registra las 3 rutas (Tabla H)."""
    # NOTA: todo lo configurable entra por argumentos; el resto sale del entorno (puntos 9 y 11).
    token_del_equipo = _resolver_token(token)
    registro = RegistroTareas(
        ejecutar,
        tope_tarea_s=tope_tarea_s,
        espera_cancelacion_s=espera_cancelacion_s,
        secretos_globales=_secretos_globales(token_del_equipo),
    )
    app = FastAPI(lifespan=_crear_lifespan(registro))
    app.state.registro = registro
    _registrar_rutas(app, registro, _crear_verificador(token_del_equipo))
    return app