# CLAUDE.md

Contexto del proyecto para Claude Code. Se carga al inicio de cada sesión — mantén este archivo corto y estable. El plan de trabajo vive en `PLAN.md`; no lo dupliques aquí.

## Qué es esto

Un recomendador de poesía personalizado. Aprende mi gusto a partir de los poemas que califico y predice si me gustará un poema nuevo. La tesis —y el sentido de toda la demo— es que un modelo entrenado con *mis* notas le gana a un LLM genérico prediciendo *mi* gusto. Construido sobre Google Cloud (Vertex AI), a la vez como pieza de portafolio y como práctica para la certificación Google PMLE.

## Arquitectura de un vistazo

App web de dos partes:
- **Vista de etiquetado** — leo un poema y lo califico (`mal` / `medio` / `me gusta`).
- **Vista de comparación** — leo un poema, lo califico y veo tres veredictos lado a lado: mi nota, la conjetura de un Gemini genérico y la predicción de mi modelo personalizado.

Camino en vivo: texto del poema → backend (Cloud Run) → features deterministas (código) + embedding (`gemini-embedding-001`) → clasificador en un endpoint de Vertex AI → predicción → comparación mostrada al usuario → todo se escribe en BigQuery.

Bucle de reentrenamiento (Vertex AI Pipeline, programado): extrae de BigQuery → valida los datos → entrena el challenger → evalúa contra el campeón actual *y* contra un baseline de Gemini genérico → compuerta campeón–challenger → si es mejor, registra en el Model Registry y actualiza el endpoint; si no, conserva el campeón.

## Stack

- Python, scikit-learn (clasificador ligero)
- Vertex AI: `gemini-embedding-001` (embeddings), endpoint (serving), Pipelines (reentrenamiento), Model Registry (versionado)
- BigQuery (almacén de datos), Cloud Run (backend + app)

## Decisiones clave — y su porqué. No las deshagas sin preguntar.

- **Las features deterministas van en Python puro, nunca en un LLM.** Número de estrofas, número de versos, longitud media de verso, diversidad léxica (type-token ratio) y densidad de puntuación se calculan en código — un LLM contaría mal y costaría dinero. El único trabajo del LLM es la *opinión del Gemini genérico* en la vista de comparación, no extraer features.
- **El modelo de embeddings es `gemini-embedding-001` (GA en Vertex AI).** No lo sustituyas por nombres viejos como `textembedding-gecko`.
- **Los embeddings se calculan una sola vez por poema al ingresarlo y se guardan en BigQuery.** Nunca re-embebas todo el corpus en una corrida de entrenamiento.
- **El clasificador se mantiene ligero** (regresión logística para empezar). Nada de redes profundas — el dataset es pequeño y el embedding hace el trabajo pesado.
- **Nunca despliegues un modelo nuevo sin pasar la compuerta campeón–challenger.** Un modelo nuevo reemplaza al de producción solo si lo supera en el set de prueba.
- **El embedding captura tema/tono; las features deterministas capturan la forma** (lo que el embedding se pierde). Ambos alimentan el clasificador.

## Guardarraíles

- **El costo es dinero real de GCP.** Prefiere tiers gratis/bajos. Avísame y espera confirmación antes de crear cualquier cosa con costo en reposo (p. ej. un endpoint dedicado de Vertex AI) o algo que escale el costo. Sugiere apagar recursos ociosos entre demos.
- **Secretos:** nunca hardcodees ni commitees credenciales ni claves de API. Usa las credenciales por defecto de `gcloud` (ADC). Mantén claves, `.env` y archivos de cuenta de servicio fuera de git.
- **Los pasos de la consola de GCP los hago yo** — crear el proyecto, activar facturación, `gcloud auth`. No asumas que puedes hacerlos tú.

## Cómo trabajar

- **Rebanada vertical primero.** Haz funcionar el camino de punta a punta de la Semana 1 (calificar poemas → entrenar → predecir) antes de construir la app o la pipeline. Mira `PLAN.md` para el orden.
- **Propón el enfoque antes de escribir mucho código.** Prefiero ver el plan primero.
- **Explica tus elecciones de producto de GCP** brevemente a medida que las haces — este proyecto es también mi estudio del PMLE, así que el razonamiento importa tanto como el código.
- **Mantén el README al día como relato de portafolio:** problema → solución → arquitectura → stack → retos → resultados.
