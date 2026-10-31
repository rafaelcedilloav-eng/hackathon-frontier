"""Contratos compartidos del agente (bloque 3). Los fija el director; los puestos los importan, no los cambian."""
from dataclasses import dataclass, field

# NOTA: tipos de tarea que entiende el intérprete; "otro" siempre termina en fallida.
TIPOS_INTENCION = ("crear", "modificar", "consultar", "exportar", "otro")
# NOTA: funciones de un control, por función y no por texto; el guarda decide por esto.
FUNCIONES_CONTROL = (
    "navegar", "abrir_formulario", "enfocar_campo", "guardar", "buscar",
    "cerrar_aviso", "leer", "paginar", "elegir_opcion", "revertir", "exportar",
    "eliminar", "otra",
)
TIPOS_ACCION = ("clic", "escribir", "tecla", "desplazar", "leer", "terminar", "fallar")
FASES = ("resolver", "crear", "modificar", "verificar", "responder", "exportar")
ESTADO_TERMINADA = "terminada"
ESTADO_FALLIDA = "fallida"
ESCALA_MODELO = 1000  # los ojos dan coordenadas de 0 a 1000


class ErrorModelo(Exception):
    """Fallo al hablar con el modelo o respuesta ilegible; nunca lleva secretos en su mensaje."""


@dataclass(frozen=True)
class Intencion:
    # NOTA: lo que pide la tarea, ya validado por código; identificador dice cómo hallar el registro.
    tipo: str
    entidad: str = ""
    identificador: dict = field(default_factory=dict)
    campos: dict = field(default_factory=dict)
    pregunta: str = ""
    filtros: dict = field(default_factory=dict)
    peligrosa: bool = False
    motivo_fallo: str = ""
    # NOTA: campos derivados de la tarea (no de la interpretación): fuera de __eq__ para no romper comparaciones viejas.
    campos_exentos: tuple = field(compare=False, default=())  # llaves cuyo valor se decide viendo la app: no se verifican contra la tarea
    permite_revertir: bool = False  # la tarea pide deshacer/restaurar: revertir es legítimo
    texto_tarea: str = field(compare=False, default="")  # texto literal de la tarea; la guarda lo usa para no confundir valor con inyección


@dataclass(frozen=True)
class Accion:
    # NOTA: una sola acción que propone el modelo; x e y van en escala 0-1000.
    tipo: str
    funcion: str = "otra"
    x: int = 0
    y: int = 0
    texto: str = ""
    tecla: str = ""
    razon: str = ""
    lectura: dict = field(default_factory=dict)
    con_clic: bool = False  # escribir con posición: primero se hace clic en x,y y luego se escribe
    veces: int = 0  # desplazar: cuántas muescas de rueda
    direccion: str = ""  # desplazar: "arriba" o "abajo"


@dataclass
class EstadoLazo:
    # NOTA: lo que el guarda necesita recordar entre acciones de una tarea.
    fase: str = "resolver"
    pasos: int = 0
    guardados: int = 0
    avisos_cerrados: int = 0  # avisos/modales cerrados con cerrar_aviso: son gratis hasta MAX_AVISOS_POR_TAREA
    exportados: int = 0  # clics con funcion exportar ejecutados; sin uno, una exportacion nunca es terminada
    posicion_guardado: tuple = ()  # coordenadas 0-1000 del clic que guardó; vacía si no hay
    campos_escritos: set = field(default_factory=set)
    bloqueos: int = 0


@dataclass(frozen=True)
class Veredicto:
    permitida: bool
    motivo: str = ""


@dataclass(frozen=True)
class Candidato:
    # NOTA: un registro que la pantalla mostró; identificador es el documento, NIT, ID o código visible.
    identificador: str
    campos: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Resolucion:
    # NOTA: tipo es "uno", "ninguno" o "ambiguo"; elegido solo existe con "uno".
    tipo: str
    elegido: Candidato | None = None
    candidatos: tuple = ()


@dataclass(frozen=True)
class Diferencia:
    campo: str
    esperado: str
    leido: str


@dataclass(frozen=True)
class RespuestaModelo:
    texto: str
    costo: float = 0.0


@dataclass(frozen=True)
class ResultadoFase:
    # NOTA: tipo es "terminar", "leer" o "fallar"; notas guarda órdenes de pantalla que se ignoraron.
    tipo: str
    lectura: dict = field(default_factory=dict)
    razon: str = ""
    notas: tuple = ()


@dataclass(frozen=True)
class ResultadoTarea:
    # NOTA: lo que arma el resumen; respuesta solo se usa en preguntas terminadas.
    estado: str
    motivo: str = ""
    campos_verificados: dict = field(default_factory=dict)
    candidatos: tuple = ()
    respuesta: tuple = ()
    notas: tuple = ()
