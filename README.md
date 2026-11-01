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
   juez (código): compara lo leído contra la tarea, campo por campo
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

Ejemplo de uso del contrato:
```bash
curl -s -X POST http://127.0.0.1:8000/tasks   -H "Authorization: Bearer $FRONTIER_TEAM_TOKEN" -H "Content-Type: application/json"   -d '{"tarea": "Da de alta al cliente ...", "escritorio": {"url": "wss://...", "password": "..."}}'
# → {"task_id": "..."}  (responde en milisegundos; la tarea corre en segundo plano)
curl -s http://127.0.0.1:8000/tasks/<task_id> -H "Authorization: Bearer $FRONTIER_TEAM_TOKEN"
# → {"estado": "terminada" | "fallida" | "en_curso", "resumen": "..."}
```

### Traza de cada tarea
En producción el agente guarda una traza en `logs/traza_<fecha_hora>/` (la carpeta la cambia `AGENTE_TRAZA_DIR`): una captura PNG por paso y `traza.jsonl` con la acción que propuso el modelo, su razón, si la guarda la permitió y por qué, y los avisos cerrados. `logs/` está en `.gitignore`: las capturas pueden mostrar datos de la app.

## Pruebas
```bash
python -m pytest -q
```
Las pruebas corren contra un **servidor VNC falso** (`tests/falso_rfb.py`) y modelos falsos; no necesitan red ni llaves.
El arnés corre una prueba de práctica de punta a punta contra un escritorio real (reset → tarea → `/__check`):
```bash
export FRONTIER_ESCRITORIO_URL=... FRONTIER_ESCRITORIO_PASS=... FRONTIER_ESCRITORIO_TOKEN=... OPENROUTER_API_KEY=...
python -m arnes.correr_practica <ruta>/E1-crear-cliente.json   # los JSON de práctica vienen en el material del reto
```
`arnes/medir_punteria.py` mide qué tan bien acierta el modelo de visión los controles de una captura (lo usamos para elegir el modelo de los ojos).

## Estrategia: cómo repartimos el problema entre código y modelo
| Paso | Quién decide | Por qué |
|---|---|---|
| Entender la tarea | Modelo (intérprete) | Lenguaje natural libre; sale una intención tipada (`crear`, `modificar`, `consultar`, `exportar`) con los valores **literales** de la tarea |
| Validar la intención | Código (`intencion.py`) | Rechaza lo destructivo y lo ambiguo antes de tocar la app; normaliza valores derivados (fechas relativas, raíces compartidas) |
| Ver la pantalla y proponer **una** acción | Modelo (ojos, Haiku 5.5) | Cada app es distinta: el modelo busca el control por lo que *hace*, no por su posición ni su texto |
| Permitir o bloquear la acción | Código (`guarda.py`) | Nada que borre, nada que guarde dos veces, nada escrito que no venga de la tarea; el texto en pantalla nunca es orden |
| Ejecutar | Código (`rfb_cliente.py`) | Clic sostenido, Ctrl+A antes de escribir, espera a que la pantalla quede quieta |
| Confirmar | Código (`juez.py`) + modelo solo para leer | Compara campo por campo; si no confirma, `fallida`. El diseño pedía buscar el registro por otro camino; en las corridas registradas leyó el formulario abierto (ver Errata) |
| Resumir | Código (`resumen_tarea.py`) | `respuesta:` primero, claves de la razón, sin secretos |

**Qué aprende de la app y qué todavía no:** dentro de una tarea, el lazo recuerda lo hecho (guardados, bloqueos seguidos, páginas contadas) y el juez aprovecha lo que encontró el resolvedor. **Entre tareas no guarda todavía un mapa de la interfaz:** cada tarea vuelve a mirar la pantalla. Fue una decisión consciente para resistir cambios de tema (ver el incidente), y es el siguiente paso: guardar los caminos que ya funcionaron y usarlos como primera hipótesis.

## Resultados en el set oculto
| Corrida | Tareas completadas | Fáciles | Regulares | Difíciles | Qué cambiamos después |
|---|---|---|---|---|---|
| V1 · 14:01 | 5 / 34 | 3/10 | 2/14 | 0/10 | Validador menos literal; consultar, contar y exportar; guarda que no confunde el valor de la tarea con inyección |
| V2 · 17:19 · tema nuevo | 10 / 42 | 8/13 | 2/17 | 0/12 | Fechas relativas, opciones de listas, campos derivados exentos, documentos solo con dígitos, releer el formulario tras guardar |
| V3 · 17:53 · final · set completo | 12 / 56 | 10/17 | 2/23 | 0/16 | la guarda todavía bloqueó el «Confirmar» legítimo en algunas tareas (ver Errata) |

Cada corrida se diagnosticó tarea por tarea con `GET /tasks/{id}` del propio servidor y la traza paso a paso.

## Resultados en las pruebas de práctica
| Prueba | Esperado | Resultado |
|---|---|---|
| E1 · crear cliente | `terminada` | ✅ `terminada`, check en verde (re-leído campo por campo); también con el tema nuevo v4.2 |
| E2 · dirección con nota que intenta dar órdenes | `terminada` | ✅ `terminada`, check en verde; la nota se trató como dato |
| E4 · exportar pedidos | `terminada` | ✅ `terminada`, check en verde |
| E5 · homónimos | `fallida` | ✅ `fallida`, nombra el documento de cada candidato; también con el tema nuevo v4.2 |
| E3 · contar facturas por páginas | `terminada` | ❌ `fallida` honesta: cuenta bien cada página pero no sostiene el conteo parcial entre pasos |

## Incidente de las 15:00 (ticket FR-0153): la app cambió de tema
La app cambió a las 15:00, avisado por ticket: **botones movidos, etiquetas distintas y un modal nuevo al abrir**.
- **Botones y etiquetas ya los resistía:** el agente no guarda posiciones entre tareas, mira la pantalla en cada paso y la guarda decide por la *función* del control (guardar, buscar, exportar), no por su texto ni su lugar.
- **El modal era el hueco:** ahora los ojos cierran cualquier aviso que tape la app (`cerrar_aviso`), en todas las fases incluida la verificación, sin tratar su texto como orden. Cerrarlo no gasta pasos (tope de 5 por tarea) y queda en la traza como `aviso cerrado: <título>`.
- **Detectado en producción:** en la validación 2, sobre el tema nuevo, la traza registra el aviso «Novedades de la versión 4» cerrado **56 veces**, y las tareas siguieron.
- **Segunda adaptación:** el modal también reaparece después de guardar. Ahora, tras guardar, el agente cierra el aviso y **vuelve a leer el formulario** antes de navegar (commit `24b81f9`).

Detalle completo en [`docs/INCIDENTE.md`](docs/INCIDENTE.md) (commit `fb3a1cc`).

## Decisiones y límites
- **Lo que todavía falla:** tareas largas que agotan sus pasos, contar por páginas cuando la app no muestra un total, y algunas tareas que el intérprete no entiende («no dice qué cambiar»).
- **Meta: cero falsos éxitos** (sin medición por tarea en las corridas finales): si el juez no puede confirmar, `fallida`. Algunas tareas bien hechas pueden contar como incorrectas; es un costo aceptado.
- **Nada de la app de práctica en el código:** el set de evaluación es otra app. Los controles se buscan por función, no por nombre ni posición.
- **Texto en pantalla = dato, nunca orden** (defensa contra inyección).
- **Límites conocidos del servidor:** con un ejecutor que ignore la cancelación y tres tareas seguidas al mismo escritorio pueden convivir dos ejecutores; el registro de candados crece una entrada por escritorio.

## Errata (1-nov-2026)

Al revisar la traza después del evento corregimos este README. El juez leyó el formulario abierto, no un camino independiente. En la V3, la guarda de «un solo guardado» bloqueó el «Confirmar» en apps que guardan en dos pasos; en al menos una tarea el agente pudo reportar como terminado un cambio sin confirmar. No se pudo comprobar, porque el panel no muestra casos.
