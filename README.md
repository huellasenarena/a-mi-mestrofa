# a-mi-mestrofa — ¿Me gustará este poema?

Un recomendador de poesía **personalizado**. Aprende mi gusto a partir de los poemas
que califico y predice si me gustará uno nuevo. La tesis: un modelo entrenado con
*mis* notas le gana a un LLM genérico prediciendo *mi* gusto.

Construido sobre Google Cloud (Vertex AI) como pieza de portafolio y práctica para la
certificación **Google Professional Machine Learning Engineer (PMLE)**.

---

## El problema
<!-- ¿Por qué un LLM genérico no basta para predecir un gusto personal? -->

## La solución
<!-- Modelo ligero entrenado sobre mis calificaciones, comparado en vivo contra Gemini genérico. -->

## Arquitectura
<!--
texto del poema → backend (Cloud Run) → features deterministas + embedding (gemini-embedding-001)
→ clasificador en Vertex AI → predicción → comparación (mi nota | Gemini genérico | mi modelo) → BigQuery
Bucle de reentrenamiento: BigQuery → valida → entrena challenger → compuerta campeón-challenger → registry/endpoint
-->

## Stack
- **Python**, scikit-learn (clasificador ligero)
- **Vertex AI**: `gemini-embedding-001`, endpoint de serving, Pipelines, Model Registry
- **BigQuery** (datos), **Cloud Run** (backend + app)

## Retos
<!-- Decisiones de diseño y qué aprendí. Se llena a medida que avanza. -->

## Resultados
<!-- Accuracy / F1 por clase, mi modelo vs baseline Gemini. La cifra que prueba la tesis. -->

---

*Proyecto en construcción. Plan de trabajo en [`PLAN.md`](./PLAN.md).*
