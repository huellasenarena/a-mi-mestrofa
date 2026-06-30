# a-mi-mestrofa — ¿Me gustará este poema?

Un recomendador de poesía **personalizado**. Aprende mi gusto a partir de los poemas
que califico y predice si me gustará uno nuevo. La tesis: un modelo entrenado con
*mis* notas le gana a un LLM genérico prediciendo *mi* gusto.

Construido sobre Google Cloud (Vertex AI) como pieza de portafolio y práctica para la
certificación **Google Professional Machine Learning Engineer (PMLE)**.

---

## El problema

El gusto poético es personal e idiosincrático. Un LLM genérico predice *calidad
percibida promedio* — no predice **a ti**. La pregunta del proyecto: ¿puede un
modelo pequeño entrenado con mis propias calificaciones superar a un LLM gigante
en la tarea de adivinar *mi* veredicto sobre un poema?

## La solución

Un clasificador ligero (regresión logística) entrenado sobre mis notas
(`no me gusta` / `medio` / `me gusta`). Cada poema se representa con dos señales
complementarias: **la forma** (features deterministas calculadas en código) y
**el tema/tono** (embedding de `gemini-embedding-001`). En vivo, cada predicción
se muestra junto a la de un Gemini genérico para comparar lado a lado.

## Arquitectura

```
texto del poema → backend (Cloud Run) → features deterministas + embedding (gemini-embedding-001)
→ clasificador en Vertex AI → predicción → comparación (mi nota | Gemini genérico | mi modelo) → BigQuery
```
Bucle de reentrenamiento (Vertex AI Pipeline, programado): BigQuery → valida →
entrena challenger → compuerta campeón–challenger → Model Registry / endpoint.

## Stack
- **Python**, scikit-learn (clasificador ligero)
- **Vertex AI**: `gemini-embedding-001`, endpoint de serving, Pipelines, Model Registry
- **BigQuery** (datos), **Cloud Run** (backend + app)

## Retos
- **Datos de origen sucios.** Los poemas venían en RTF; la conversión a texto
  colapsaba algunos versos. Detectar saltos de verso por `\n` *o* corridas de
  espacios recupera el conteo de forma. (Lección: el grueso del ML es limpiar datos.)
- **Pocos datos (n=50), p ≫ n.** Con 50 poemas y un embedding de cientos de
  dimensiones, el riesgo es sobreajuste. Mitigación: dimensión de embedding
  reducida, regularización L2 fuerte y **leave-one-out CV** (un holdout fijo
  sería puro ruido a este tamaño).
- **Evaluación honesta.** Se compara siempre contra un piso (clase mayoritaria)
  y contra el Gemini genérico, en accuracy *y* F1-macro (la métrica justa con
  clases desbalanceadas).

## Resultados

Primera evaluación con **50 poemas** (3 clases, leave-one-out CV):

| Modelo | Accuracy | F1-macro |
|---|---:|---:|
| Piso (clase mayoritaria) | 0.440 | 0.204 |
| Gemini genérico | 0.240 | 0.129 |
| **Modelo personalizado** | 0.440 | **0.399** |

En F1-macro el modelo personalizado **casi duplica el piso y triplica al Gemini
genérico** — la tesis se sostiene incluso con datos mínimos. En la tarea binaria
(*me gusta* vs *no me gusta*) alcanza **0.684** vs piso 0.579.

**Hallazgo:** a n=50 la señal viene de las **features de forma**, no del
embedding (que con tan pocos datos sobreajusta). El corpus crece a diario y
`data/historial.csv` registra una **curva de aprendizaje** para ver *cuándo* el
embedding empieza a aportar — el portafolio cuenta una historia con movimiento,
no una foto fija.

---

*Proyecto en construcción. Plan de trabajo en [`PLAN.md`](./PLAN.md).*
