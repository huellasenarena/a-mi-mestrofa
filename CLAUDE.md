# CLAUDE.md

Contexto del proyecto para Claude Code. Se carga al inicio de cada sesión — mantén este archivo corto y estable. El plan de trabajo vive en `PLAN.md`; no lo dupliques aquí.

## Qué es esto

Un recomendador de poesía personalizado. Aprende mi gusto a partir de los poemas que califico y predice si me gustará un poema nuevo. La tesis —y el sentido de toda la demo— es que un modelo entrenado con *mis* notas le gana a un LLM genérico prediciendo *mi* gusto. Construido sobre Google Cloud (Vertex AI), a la vez como pieza de portafolio y como práctica para la certificación Google PMLE.

## Arquitectura de un vistazo

App web de dos partes:
- **Vista de etiquetado** — leo un poema y lo califico (`mal` / `medio` / `me gusta`).
- **Vista de comparación** — leo un poema, lo califico y veo tres veredictos lado a lado: mi nota, la conjetura de un Gemini genérico y la predicción de mi modelo personalizado.

Camino en vivo (`servidor/`, en Cloud Run desde el 12 sep 2026): texto del poema → embedding (`gemini-embedding-001`) → clasificador cargado en memoria dentro del contenedor (no en un endpoint de Vertex: cobraría en reposo) → predicción + Gemini genérico → las predicciones de cada día del blog se congelan en BigQuery. Detalle en `docs/conexion-qmp.md`.

Bucle de reentrenamiento (Vertex AI Pipeline, programado): extrae de BigQuery → valida los datos → entrena el challenger → evalúa contra el campeón actual *y* contra un baseline de Gemini genérico → compuerta campeón–challenger → si es mejor, registra en el Model Registry y actualiza el endpoint; si no, conserva el campeón.

## Stack

- Python, scikit-learn (clasificador ligero)
- Vertex AI: `gemini-embedding-001` (embeddings), Gemini (baseline), Pipelines (reentrenamiento), Model Registry (versionado)
- BigQuery (almacén de datos), Cloud Run (servidor FastAPI, escala a cero), Cloud Scheduler, Cloud Storage (modelo)

## Decisiones clave — y su porqué. No las deshagas sin preguntar.

- **Las features deterministas suponen forma en verso.** Número de estrofas, versos y longitud media de verso son ruido en un poema en prosa, y el corpus tiene varios. Antes de juzgar cuánto aportan, separar los dos casos.
- **Las features deterministas van en Python puro, nunca en un LLM.** Número de estrofas, número de versos, longitud media de verso, diversidad léxica (type-token ratio) y densidad de puntuación se calculan en código — un LLM contaría mal y costaría dinero. El único trabajo del LLM es la *opinión del Gemini genérico* en la vista de comparación, no extraer features.
- **El modelo de embeddings es `gemini-embedding-001` (GA en Vertex AI).** No lo sustituyas por nombres viejos como `textembedding-gecko`.
- **Los embeddings se calculan una sola vez por poema al ingresarlo y se guardan en BigQuery.** Nunca re-embebas todo el corpus en una corrida de entrenamiento.
- **El clasificador se mantiene ligero** (regresión logística para empezar). Nada de redes profundas — el dataset es pequeño y el embedding hace el trabajo pesado.
- **Cada día del blog se predice una vez y la predicción no se toca nunca**, antes de que su nota entre al corpus. Es lo que hace honesto el marcador público. No recalcular días guardados ni predecir en vivo en `/hoy`.
- **Nunca despliegues un modelo nuevo sin pasar la compuerta campeón–challenger.** Un modelo nuevo reemplaza al de producción solo si lo supera en el set de prueba.
- **El embedding captura tema/tono; las features deterministas capturan la forma** (lo que el embedding se pierde). Ambos alimentan el clasificador. *(Curva medida en `data/historial.csv`, F1-macro a 3 clases. A n=50 (29 jun) el embedding sobreajustaba y la señal venía de la forma: `feat` 0.399 vs `emb` 0.244. **A n=187 (10 sep) se invirtió: `emb` 0.424 vs `feat` 0.349**, y las features de forma caen por debajo del piso de clase mayoritaria. Sumarlas al embedding ahora resta un poco (`emb+feat` 0.413). No quitarlas todavía: parte de la caída se explica porque el corpus incluye poemas en prosa, donde "nº de versos" o "longitud media de verso" no describen nada. Volver a medir al crecer el corpus.)*
- **El corpus es solo en español.** No mezclar idiomas o el modelo aprendería "idioma" en vez de gusto. Implica que no hay API limpia de poemas aleatorios (PoetryDB es inglés); cualquier captura automática iría por scraping.

## Proyecto hermano — Que Mal Poema

`~/Desktop/qmp` · [quemalpoema.com](https://quemalpoema.com) · **repo aparte, a propósito.**

Plataforma de publicación poética diaria del mismo autor: cada entrada lleva un poema propio, un poema citado de otro autor y un análisis. Es la fuente natural de poemas calificados para este proyecto — ya lee y juzga un poema ajeno al día.

**Los repos no se fusionan** (decidido 10 sep 2026): el repo de QMP *es* el sitio (GitHub Pages sirve desde la raíz), así que todo lo que se meta ahí queda publicado, incluidos los poemas ajenos completos de `data/poemas.csv` y las calificaciones personales. Se conectan por datos: QMP publica `archivo.json` y los `.txt` por HTTPS, y este proyecto los consume. Acoplamiento en un solo sentido — el blog no puede romperse por un fallo de aquí.

Diseño completo, trampas del pipeline y decisiones abiertas: [`docs/conexion-qmp.md`](./docs/conexion-qmp.md).

## Guardarraíles

- **El costo es dinero real de GCP.** Prefiere tiers gratis/bajos. Avísame y espera confirmación antes de crear cualquier cosa con costo en reposo (p. ej. un endpoint dedicado de Vertex AI) o algo que escale el costo. Sugiere apagar recursos ociosos entre demos.
- **Secretos:** nunca hardcodees ni commitees credenciales ni claves de API. Usa las credenciales por defecto de `gcloud` (ADC). Mantén claves, `.env` y archivos de cuenta de servicio fuera de git.
- **Los pasos de la consola de GCP los hago yo** — crear el proyecto, activar facturación, `gcloud auth`. No asumas que puedes hacerlos tú.

## Cómo trabajar

- **Rebanada vertical primero.** Haz funcionar el camino de punta a punta de la Semana 1 (calificar poemas → entrenar → predecir) antes de construir la app o la pipeline. Mira `PLAN.md` para el orden.
- **Propón el enfoque antes de escribir mucho código.** Prefiero ver el plan primero.
- **Explica tus elecciones de producto de GCP** brevemente a medida que las haces — este proyecto es también mi estudio del PMLE, así que el razonamiento importa tanto como el código.
- **Mantén el README al día como relato de portafolio:** problema → solución → arquitectura → stack → retos → resultados.
