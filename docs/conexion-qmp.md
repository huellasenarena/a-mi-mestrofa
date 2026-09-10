# Conexión con Que Mal Poema

Diseño acordado el 10 sep 2026. Nada de esto está implementado todavía: es el
punto de partida para la sesión que lo construya.

## Qué se quiere

El autor publica un poema al día en [quemalpoema.com](https://quemalpoema.com)
(repo `~/Desktop/qmp`): un poema propio, un **poema citado** de otro autor y un
análisis en prosa. Ya lee y juzga un poema ajeno cada día — es la fuente natural
de datos calificados para este recomendador.

Dos cosas, entonces:

1. Que al escribir una entrada, la nota de gusto del poema citado entre al
   corpus de entrenamiento de este proyecto.
2. Que el blog enlace a este proyecto, y a poder ser muestre la predicción.

## Decisión: los repos NO se fusionan

**El repo de QMP *es* el sitio web** — GitHub Pages sirve desde la raíz. Todo lo
que se meta ahí queda publicado. Fusionar dejaría `data/poemas.csv` (187 poemas
ajenos completos + las calificaciones personales del autor) descargable en
`quemalpoema.com/data/poemas.csv`. Eso no es cita como lo es publicar un poema
al día con autor, libro y análisis alrededor.

Además: `main` de QMP es producción y lleva nueve meses de racha diaria; tiene
una rama `reorganize` sin mergear; y sus secretos (service account de Google
Docs, clave de OpenAI) no son los de este proyecto (ADC de GCP, Vertex).

Se conectan **por datos**, no por git.

## El contrato — ya existe

QMP publica una API consumible sin cambio alguno. Verificado el 10 sep 2026:

| Recurso | Estado |
|---|---|
| `https://www.quemalpoema.com/data/archivo.json` | HTTP 200 · 308 KB · `application/json` · 164 entradas |
| `https://www.quemalpoema.com/data/textos/YYYY/MM/YYYY-MM-DD.txt` | HTTP 200 · el texto de la entrada |

Ojo: `quemalpoema.com` redirige (301) a `www.quemalpoema.com` — seguir redirecciones.

El `.txt` trae el poema citado bajo `# POEMA_CITADO`. `archivo.json` guarda
**sólo metadatos** (fecha, poeta, títulos, keywords), nunca texto de poema — es
un invariante de aquel proyecto, respetarlo.

Lo único que falta en esa API es la nota de gusto.

## Capturar la nota — el truco que ya funcionó allí

QMP añadió la transparencia IA con marcadores en texto plano que viajan intactos
por todo el pipeline (iA Writer → Atajo → Apps Script → Google Docs → pull) y se
separan al final en `core/ia_sections.py::split_ia_markers`. **Cero cambios en el
atajo, el Apps Script, el esquema de Docs o los YAML.** La nota debe ir igual.

Tres trampas encontradas al revisar el código:

1. **`## Notas` ya está ocupado.** `atajo.js` lo parsea y lo enruta a otro tab de
   Google Docs (`TAB_NOTAS_POEMAS` / `TAB_NOTAS_ANALISIS`); no viaja dentro del
   análisis y el pull nunca lo vería. Usar un marcador distinto: **`## Gusto`**.
2. **`# CONVERSACION` se lee verbatim hasta el final del archivo** y se traga lo
   que venga después. El marcador nuevo tiene que ir ANTES:

   ```
   ## Borrador final
   ...
   ## Gusto
   3
   ## Conversación con IA
   https://claude.ai/share/...
   ```

   Puesto después del enlace no da error: simplemente no llega. `validate_entry.py`
   debería rechazarlo explícitamente — un fallo silencioso más es justo lo que
   este proyecto acaba de pagar caro (ver el bug del baseline, commit 330d008).
3. **El dato no siempre existe.** De las 164 entradas, **139 tienen texto de
   poema citado y 25 están en modo PDF** (poemas visuales, sin texto). Y no todas
   las 139 son poema en español: la del 2026-08-24 cita un cuento de Hawthorne.
   El corpus es solo español (decisión clave de `CLAUDE.md`), así que hace falta
   un filtro — y lo prudente es que el importador salte lo que no pueda decidir y
   lo liste para confirmación manual, en vez de adivinar.

La nota es metadato, así que cabe en `archivo.json` sin romper su invariante.

## El importador (lado de este repo)

`src/importar_qmp.py`: lee `archivo.json` + los `.txt`, extrae `# POEMA_CITADO`,
filtra (modo PDF, idioma), deduplica por clave de origen `qmp:YYYY-MM-DD` y
añade a `data/poemas.csv` con columnas `fuente` y `fecha_origen`. Idempotente,
sin infraestructura, sin costo. Cuando existan Cloud Run + BigQuery (Bloques F y
G del `PLAN.md`) se cambia el destino y el código de extracción no se toca.

**Pull, no push:** QMP no sabe que este proyecto existe; este proyecto consume una
API pública. El acoplamiento va en un solo sentido y el blog no puede romperse
por un fallo de aquí.

## El orden que hace honesta la evaluación

Si el modelo predice **antes** de que la nota entre al entrenamiento, cada entrada
del blog es un punto de test fuera de muestra. Eso da un marcador público que se
actualiza solo ("va 34 de 78 desde septiembre"), imposible de acusar de haber
elegido el split. Es el mejor argumento de portafolio que tiene la conexión, y
sólo cuesta respetar el orden de las operaciones.

## Riesgo a vigilar: sesgo de selección

Los poemas citados son los que el autor eligió publicar — se inclinarán a
"me gusta". Si llegan casi todos con nota 3, el flujo aporta poca señal
discriminativa. Mitigación: calificar con la escala completa y seguir alimentando
el lado "no me gusta" por `data/nuevos.txt`.

## Decisiones abiertas — preguntar, no asumir

1. **¿Qué poema entra?** Recomendación: sólo el citado. El poema propio del autor
   no sirve como señal (lo calificaría siempre alto, y está en su voz, así que el
   modelo aprendería "esto lo escribió él" en vez de "esto le gusta"). Pendiente
   también si se descartan traducciones, para no aprender el estilo del traductor.
2. **¿Importación retroactiva de los ~139 ya publicados?** Casi duplicaría el
   corpus (187 → ~320), que es la palanca más grande disponible. Cuesta
   calificarlos a mano, aunque son poemas ya leídos y analizados a fondo.
3. **¿Qué muestra el blog?** Enlace estático ya, o marcador por entrada
   ("mi modelo predijo X · mi nota fue Y") precalculado al publicar — esto último
   necesita el modelo servible del Bloque F.

## Dónde está el modelo hoy (10 sep 2026)

187 poemas calificados. En duelo con datos idénticos (40 de entrenamiento, 147 de
test): modelo `emb+feat` **F1-macro 0.410**, Gemini con esos mismos 40 ejemplos en
el prompt 0.340, Gemini genérico 0.280, piso 0.209. Detalle en `README.md` y en
la curva de `data/historial.csv`.
