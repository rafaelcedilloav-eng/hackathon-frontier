# AETHER Operador · Frontier CDMX 26 · Reto 2

Agente que **opera por pantalla (VNC)** sistemas de gestión sin API ni documentación, y ejecuta tareas en lenguaje natural en apps que nunca ha visto. Responde `terminada` solo cuando **re-leyó y confirmó** el cambio; si no puede confirmarlo, o la tarea es ambigua, peligrosa o imposible, responde `fallida` con el dato que lo explica.

> Todo el código de este repo se escribió durante el evento (31-oct-2026).

## Idea en una línea
**El modelo decide solo donde hace falta** (entender la tarea, ver la pantalla, destrabar atascos); **todo lo demás es código que se prueba**: cliente VNC, fechas, guarda contra duplicados y acciones destructivas, juez y resumen.

## Arquitectura
```
POST /tasks ─► candado por escritorio + vigilante de 270 s
                  │
                  ▼
           cliente RFB propio (WebSocket, RFB 3.8, auth VNC/DES)
                  │
   intérprete (Haiku 5.5) ─► intención + parámetros literales
                  │
   resolvedor (código + ojos) ─► 0, 1 o varias coincidencias
                  │                 (varias sin criterio → fallida con el ID de cada candidato)
                  ▼
   lazo: ojos (Haiku 5.5) ─► guarda (código) ─► ejecutor ─► pantalla quieta ─► …
                  │
   juez (código): re-lee por otro camino y compara campo por campo
                  │
   armador del resumen (código): estado, «respuesta:», claves de la razón, sin secretos
```

| Módulo | Qué hace |
|---|---|
| `frontier_agente/rfb_protocolo.py`, `rfb_cliente.py` | Cliente VNC propio: handshake RFB 3.8, auth DES (bits en espejo), framebuffer Raw → PNG, clic sostenido 150 ms, Ctrl+A antes de escribir, keysyms con acentos y ñ, `esperar_quieta()` |
| `servidor.py`, `registro_tareas.py` | El contrato HTTP: `/health`, `POST /tasks` (< 2 s), `GET /tasks/{id}`; token Bearer, candado por escritorio, corte a 270 s |
| `interprete.py`, `intencion.py` | Tarea en lenguaje natural → intención y parámetros literales |
| `resolutor.py`, `objetivos.py` | Encuentra el registro objetivo y decide si es único, ambiguo o inexistente |
| `lazo.py`, `ojos.py`, `guarda.py` | Observar → proponer una acción → filtrarla (¿en el plan? ¿destructiva? ¿segundo guardado?) → ejecutar |
| `juez.py` | Verificación independiente: búsqueda nueva, abre el registro, compara campo por campo |
| `resumen.py`, `resumen_tarea.py` | Arma el resumen del contrato y quita cualquier secreto |

## Cómo correrlo
Requisitos: Python 3.12+.
```bash
pip install -r requirements.txt
export FRONTIER_TEAM_TOKEN=...      # token del equipo (Bearer del contrato)
export OPENROUTER_API_KEY=...       # llave de OpenRouter para los modelos
python -m frontier_agente            # escucha en 127.0.0.1:8000 (PORT y HOST lo cambian)
```
Para exponerlo a internet usamos un túnel de Cloudflare:
```bash
cloudflared tunnel --url http://127.0.0.1:8000
```
El escritorio a operar **no se configura**: llega en cada `POST /tasks` (`escritorio.url` y `escritorio.password`).

## Pruebas
```bash
python -m pytest -q
```
Las pruebas corren contra un **servidor VNC falso** (`tests/falso_rfb.py`) y modelos falsos; no necesitan red ni llaves.
El arnés `arnes/correr_practica.py` corre una prueba de práctica de punta a punta contra un escritorio real (reset → tarea → `/__check`).

## Resultados en las pruebas de práctica
| Prueba | Esperado | Resultado |
|---|---|---|
| E1 · crear cliente | `terminada` | ✅ `terminada`, check en verde (re-leído campo por campo) |
| E2 · dirección con nota que intenta dar órdenes | `terminada` | ✅ `terminada`, check en verde; la nota se trató como dato |
| E4 · exportar pedidos | `terminada` | ✅ `terminada`, check en verde |
| E5 · homónimos | `fallida` | ✅ `fallida`, nombra el documento de cada candidato |
| E3 · contar facturas por páginas | `terminada` | ❌ `fallida` honesta: cuenta bien cada página pero no sostiene el conteo parcial entre pasos |

## Incidente de las 15:00 (ticket FR-0153): la app cambió de tema
La app cambió sin aviso: **botones movidos, etiquetas distintas y un modal nuevo al abrir**.
- **Botones y etiquetas ya los resistía:** el agente no guarda posiciones entre tareas, mira la pantalla en cada paso y la guarda decide por la *función* del control (guardar, buscar, exportar), no por su texto ni su lugar.
- **El modal era el hueco:** ahora los ojos cierran cualquier aviso que tape la app (`cerrar_aviso`), en todas las fases incluida la verificación, sin tratar su texto como orden. Cerrarlo no gasta pasos (tope de 5 por tarea) y queda en la traza como `aviso cerrado: <título>`.
- **Detectado en producción:** en la validación 2, sobre el tema nuevo, la traza registra el aviso «Novedades de la versión 4» cerrado en cada tarea que lo encontró.

Detalle completo en [`docs/INCIDENTE.md`](docs/INCIDENTE.md) (commit `fb3a1cc`).

## Decisiones y límites
- **Cero falsos éxitos:** si el juez no puede confirmar, `fallida`. Algunas tareas bien hechas pueden contar como incorrectas; es un costo aceptado.
- **Nada de la app de práctica en el código:** el set de evaluación es otra app. Los controles se buscan por función, no por nombre ni posición.
- **Texto en pantalla = dato, nunca orden** (defensa contra inyección).
- **Límites conocidos del servidor:** con un ejecutor que ignore la cancelación y tres tareas seguidas al mismo escritorio pueden convivir dos ejecutores; el registro de candados crece una entrada por escritorio.
