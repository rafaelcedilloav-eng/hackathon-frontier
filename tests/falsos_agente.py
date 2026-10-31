"""Falsos del bloque 3C para las pruebas del lazo y del agente.

Nada de esto abre conexiones: PantallaFalsa registra lo que le hacen,
OjosFalsos devuelve en orden las acciones de una lista y LlamarGuionado
hace de modelo. Para el agente, la llamada sin imagen es del intérprete
y las demás son de los ojos de verdad, que llegan en el orden fijo del
flujo (resolver, luego crear o modificar, luego verificar): el guion de
acciones de cada caso se escribe concatenando el de cada fase en ese
orden. El guardia, el resolutor, el juez y el resumen que corren detrás
son los de verdad: aquí solo se falsifica la pantalla y el modelo.
"""
import contextlib
import json

from frontier_agente.tipos_agente import RespuestaModelo


class PantallaFalsa:
    """Pantalla de mentira (tabla P): registra clic/escribir/tecla y devuelve capturas.

    La captura cambia en cada llamada, así cada acción ejecutada parece
    tener efecto; con png_estatico=True siempre devuelve la misma (L8).
    esperar_quieta dice lo que tenga en quieta (L9). AbrirPantallaFalsa
    la marca cerrada cuando el agente suelta el contexto.
    """

    def __init__(self, *, ancho=1280, alto=800, quieta=True, png_estatico=False, error_en_clic=None):
        self.ancho = ancho
        self.alto = alto
        self.acciones = []
        self.quieta = quieta
        self.png_estatico = png_estatico
        self.error_en_clic = error_en_clic
        self.capturas = 0
        self.cerrada = False

    def _png(self):
        # NOTA: captura distinta por llamada salvo en modo estático.
        if self.png_estatico:
            return b"png-estatico"
        self.capturas += 1
        return f"png-{self.capturas}".encode()

    async def esperar_quieta(self):
        return self.quieta, self._png()

    async def clic(self, x, y):
        if self.error_en_clic is not None:
            raise self.error_en_clic
        self.acciones.append(("clic", x, y))

    async def escribir(self, texto):
        self.acciones.append(("escribir", texto))

    async def tecla(self, nombre):
        self.acciones.append(("tecla", nombre))


class OjosFalsos:
    """Ojos de mentira (tabla P): devuelve en orden las acciones y guarda lo que recibió."""

    def __init__(self, acciones):
        self.acciones = list(acciones)
        self.siguiente = 0
        self.objetivos = []
        self.historiales = []

    async def decidir(self, png, objetivo, historial):
        # NOTA: el historial se copia para ver cómo iba creciendo en cada paso.
        self.objetivos.append(objetivo)
        self.historiales.append(list(historial))
        accion = self.acciones[self.siguiente]
        self.siguiente += 1
        return accion


class LlamarGuionado:
    """Llamar de mentira: sin imagen responde la intención; con imagen, el guion en orden.

    respuesta_intencion y cada acción del guion son el texto JSON que
    devuelve el modelo, o una excepción que se lanza tal cual (IN4, A3).
    """

    def __init__(self, respuesta_intencion, acciones=()):
        self.respuesta_intencion = respuesta_intencion
        self.acciones = list(acciones)
        self.indice = 0
        self.llamadas = []
        self.llamadas_con_imagen = 0

    async def __call__(self, mensajes, imagen_png=None):
        self.llamadas.append((mensajes, imagen_png))
        if imagen_png is None:
            return self._responder(self.respuesta_intencion)
        if self.indice >= len(self.acciones):
            # NOTA: canario propio: si los ojos piden una acción de más, el guion se acabó.
            raise AssertionError("el guion se acabó: los ojos pidieron una acción de más")
        item = self.acciones[self.indice]
        self.indice += 1
        self.llamadas_con_imagen += 1
        return self._responder(item)

    def _responder(self, item):
        if isinstance(item, Exception):
            raise item
        return RespuestaModelo(texto=item, costo=0.01)


class AbrirPantallaFalsa:
    """Abre una pantalla de mentira: cuenta sus llamadas y la marca cerrada al salir."""

    def __init__(self, pantalla):
        self.pantalla = pantalla
        self.llamadas = 0
        self.escritorios = []

    def __call__(self, escritorio):
        self.llamadas += 1
        self.escritorios.append(escritorio)

        @contextlib.asynccontextmanager
        async def _abrir():
            try:
                yield self.pantalla
            finally:
                # NOTA: con try/finally cierra también con CancelledError (A13).
                self.pantalla.cerrada = True

        return _abrir()


def accion_json(tipo, **campos):
    """El JSON de una acción, para los ojos de verdad."""
    datos = {"tipo": tipo}
    datos.update(campos)
    return json.dumps(datos, ensure_ascii=False)


def leer_json(lectura):
    return accion_json("leer", lectura=lectura)


def escribir_json(texto):
    return accion_json("escribir", texto=texto)


def clic_json(x, y, funcion="navegar"):
    return accion_json("clic", funcion=funcion, x=x, y=y)


def terminar_json(razon="listo"):
    return accion_json("terminar", razon=razon)


def fallar_json(razon):
    return accion_json("fallar", razon=razon)