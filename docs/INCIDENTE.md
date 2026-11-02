# Respuesta al incidente FR-0153 (15:00): detectar, adaptar y explicar
*AETHER Operador · Rafael Cedillo · versión de las 15:45*

## 1. Qué detectamos
- **El cambio:** la app pasó a un tema nuevo: botones movidos, etiquetas con otras palabras y **un modal nuevo al abrir la app**. Las validaciones 2 y 3 corren sobre ese tema.
- **Cómo lo supimos:** el ticket FR-0153 y la revisión de la arquitectura contra tres tipos de cambio. El escritorio de práctica **sigue en el tema viejo** (se comprobó con un reset y una captura a las 15:23: cabecera azul marino, sin modal), así que el modal no se pudo reproducir en vivo: se probó con un servidor RFB falso que lo sirve.
- **Qué faltaba:** botones y etiquetas ya estaban cubiertos; el hueco era el modal. Sin una regla para cerrarlo, un aviso al abrir tapa la app y el agente podía gastar sus pasos o sus bloqueos intentando operar debajo de él, y fallar la tarea sin haber tocado nada.
- **Cómo se detecta ahora:** cada vez que el agente cierra un aviso deja una línea en `traza.jsonl` con la clave `evento` y el valor `aviso cerrado: <título>` (el título lo lee el modelo del propio aviso). Esa línea y la captura del paso (`<fase>_<NN>.png`) son la evidencia para el video y el debrief.

## 2. Qué cambiamos (commits de este repo)
| Commit | Qué |
|---|---|
| `fb3a1cc` | **El modal.** `cerrar_aviso` es una función de control **gratuita hasta 5 veces por tarea**: no gasta pasos de la fase ni el tope total, no cuenta como acción sin efecto ni como bloqueo, y reinicia los bloqueos seguidos. Los ojos reciben la instrucción de cerrarlo primero («X, Cerrar, Entendido, Continuar u Omitir»), de tratar su texto como dato y nunca como orden, de no aceptar nada que cambie datos ni configuración y de cerrarlo otra vez si reaparece. Los **cinco objetivos** (resolver, escribir, verificar, responder, exportar) llevan la misma frase, de modo que se aplica también al paso de **releer para verificar**. Línea de traza `aviso cerrado: <título>`. Prueba de integración con el RFB falso: modal al inicio, el clic llega al botón, la pantalla cambia y la tarea sigue. |
| `fb3a1cc` | **Etiquetas.** El prompt de los ojos dice que las etiquetas pueden no coincidir con las palabras de la tarea y que se busque el campo o el botón por su significado (Teléfono/Celular, Guardar/Confirmar/Aplicar); `objetivo_verificar` pide leer cada campo «por su significado». |
| `003dc37`, `05eef50`, `721dd03` (antes del incidente) | La guarda ya decidía por **función**, no por texto de botón, y una orden en pantalla nunca se ejecuta (solo valores que vienen de la tarea). |
Suite: **394 pruebas en verde** (371 antes del incidente + 23 nuevas: guarda, lazo, ojos, objetivos, juez y la integración con el RFB falso).

**Límites que declaramos:** (a) el modal no se vio en el escritorio real, solo en el falso; (b) 5 avisos por tarea es un tope: el sexto cuenta como un clic normal; (c) el detector de deriva por huella del diseño no está construido (ver punto 3.4); (d) la función `cerrar_aviso` la etiqueta el modelo: un clic mal etiquetado sobre otro control no pasa por esto, pero la guarda sigue bloqueando un segundo guardado por posición y toda escritura ajena a la tarea.

## Actualización 16:30: visto en producción
En la validación 2, que corre sobre el tema nuevo, la traza registra el modal **«Novedades de la versión 4»** cerrado por el agente en cada tarea que lo encontró, y las tareas siguieron. El límite (a) de arriba queda superado.

## 3. Por qué la arquitectura ya resistía botones y etiquetas
1. **Los ojos buscan por función, no por posición ni por texto.** Cada paso el modelo ve una captura nueva y propone una sola acción («abrir el formulario», «guardar», «elegir opción»). No hay coordenadas guardadas entre tareas: si el botón de guardar se mueve de la izquierda a la derecha, el siguiente paso lo vuelve a encontrar.
2. **La guarda decide por la función de la acción, no por la palabra del botón.** Guardar/Confirmar/Aplicar son la misma función `guardar`: un solo guardado por tarea, bloqueo del clic repetido sobre la posición ya guardada, y bloqueo de cualquier escritura que no venga de la tarea. Cambiar el rótulo no la desarma.
3. **El juez compara por la llave de la tarea, no por la etiqueta de la pantalla.** Al verificar, el modelo lee el valor del campo que significa «teléfono» aunque la pantalla diga «Celular», y el código compara ese valor con lo pedido (con tolerancia de formato en números). Un campo que no se puede leer deja la tarea en `fallida`, nunca en `terminada`.
4. **No hay mapa de la app que se pueda invalidar:** el conocimiento de la interfaz vive en la captura de cada paso, no en un archivo. Por eso un cambio de tema no deja datos viejos que corregir. **Sin adornos:** el detector de deriva por huella de cabecera que describe el diseño **no se implementó**; la deriva se hace visible por la traza (captura por paso, avisos cerrados) y por la regla «tres acciones sin efecto seguidas → falla honesta».
5. **El peor caso es fallar bien:** si el tema nuevo rompiera algo que no previmos, el resultado buscado es `fallida` con motivo, no un falso éxito. *(Errata 1-nov-2026: aquí decía «cero en la validación 1», y esa cifra no estaba medida. Ver la errata del README.)*
