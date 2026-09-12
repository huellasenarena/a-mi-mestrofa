# Conexión con Que Mal Poema

Diseño acordado el 10 sep 2026. **Construido el 12 sep 2026**: la nota viaja
por el pipeline de QMP y se publica en `archivo.json`, y `src/importar_qmp.py`
la trae al corpus de aquí. Lo que falta es el servidor — ver el final.

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

La nota de gusto ya está ahí: `analysis.gusto`, un entero 1/2/3, presente sólo
en las entradas que la llevan.

## Capturar la nota — hecho

El autor escribe `## Gusto` con un 1, 2 o 3 después del análisis en iA Writer.
Viaja intacto por todo el pipeline (iA Writer → Atajo → Apps Script → Google Docs
→ pull) y se separa en `core/ia_sections.py::split_ia_markers`. **Cero cambios en
el atajo, el Apps Script, el esquema de Docs o los YAML**, como se esperaba.
Probado de punta a punta el 12 sep: una entrada de prueba se publicó sola en la
barrida de las 06:00 y llegó con `analysis.gusto = 2`.

Es **obligatoria** desde el 12 sep 2026 (`GUSTO_DESDE` en `validate_entry.py`):
si falta, la entrada no se publica. La sección va siempre, también los días de
PDF, donde se escribe vacía. Las 164 entradas anteriores quedan exentas.

Las tres trampas que se habían previsto, y cómo quedaron:

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

   **Resuelto mejor de lo previsto:** `split_ia_markers` corta cada marcador
   hasta el siguiente que aparezca, así que el orden en iA Writer ya da igual —
   una nota escrita después del enlace se captura igual. El `.txt` sale siempre
   en orden canónico, y `validate_entry.py` rechaza cualquier otro.
3. **El dato no siempre existe.** De las 164 entradas, **139 tienen texto de
   poema citado y 25 están en modo PDF** (poemas visuales, sin texto). Y no todas
   las 139 son poema en español: la del 2026-08-24 cita un cuento de Hawthorne.
   El corpus es solo español (decisión clave de `CLAUDE.md`), así que hace falta
   un filtro — y lo prudente es que el importador salte lo que no pueda decidir y
   lo liste para confirmación manual, en vez de adivinar.

La nota es metadato, así que cabe en `archivo.json` sin romper su invariante.

## El importador (lado de este repo)

`src/importar_qmp.py` — **hecho el 12 sep 2026.** Lee `archivo.json` + los
`.txt`, extrae `# POEMA_CITADO`, deduplica por clave de origen `qmp:YYYY-MM-DD`
y añade a `data/poemas.csv` con columnas `fuente` y `fecha_origen` (que se
añaden solas la primera vez; las 187 filas originales las llevan vacías).
Idempotente, sólo biblioteca estándar, sin infraestructura, sin costo.

    python src/importar_qmp.py             # enseña qué añadiría, no escribe
    python src/importar_qmp.py --aplicar   # lo añade

Las entradas en modo PDF se caen solas (no hay texto). **No filtra por idioma**:
un detector sería otra dependencia y se equivocaría con poemas cortos, así que
el script no escribe hasta que mires la lista y pases `--aplicar`. Es un poema
al día; mirarlo cuesta nada.

Cuando existan Cloud Run + BigQuery (Bloques F y G del `PLAN.md`) se cambia el
destino y el código de extracción no se toca.

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
2. ~~**¿Importación retroactiva de los ~139 ya publicados?**~~ **Decidido el 12
   sep: no.** El autor ya calificó 187 a mano y no quiere calificar más. El
   corpus crece a un poema al día desde ahora.
3. ~~**¿Qué muestra el blog?**~~ **Hecho:** `site/mestrofa.html` en el repo de
   QMP, publicado el 12 sep. Enseña el poema citado del día, tres números (nota
   real · mi modelo · modelo genérico) y una caja para predecir cualquier texto.
   Lee una sola constante, `API_BASE`, hoy apuntando a unos JSON de ejemplo.

## Lo que falta — el servidor

Esto es lo único que queda, y es todo de este lado:

- **`GET /hoy`** → la forma exacta está en `data/mestrofa-demo.json`. Campos:
  `fecha`, `poeta`, `titulo`, `libro`, `texto_url`, `hay_duelo`, `gusto`,
  `pred_modelo`, `pred_gemini`, `predicho_el`, `marcador`.
- **`POST /predecir`** con `{"texto": "…"}` → `data/mestrofa-demo-predecir.json`:
  `modelo`, `gemini`, `probs`, `aviso`.
- **`fecha_duelo`** en `/hoy`: cuando el día de hoy no tiene poema en texto, la
  página enseña los números del último día que sí lo tuvo, y necesita saber de
  qué día son para decirlo. Sin ese campo enseña "no encontré nada".
- Cambiar `API_BASE` en `site/mestrofa.js` (una línea) y CORS para
  `quemalpoema.com`.

**El orden importa:** el modelo tiene que predecir *antes* de que la nota entre
al entrenamiento, o el marcador público deja de ser honesto.

## Dónde está el modelo hoy (10 sep 2026)

187 poemas calificados. En duelo con datos idénticos (40 de entrenamiento, 147 de
test): modelo `emb+feat` **F1-macro 0.410**, Gemini con esos mismos 40 ejemplos en
el prompt 0.340, Gemini genérico 0.280, piso 0.209. Detalle en `README.md` y en
la curva de `data/historial.csv`.
