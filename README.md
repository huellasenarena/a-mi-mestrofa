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
- **Pocos datos, p ≫ n.** Con decenas de poemas y un embedding de cientos de
  dimensiones, el riesgo es sobreajuste. Mitigación: dimensión de embedding
  reducida, regularización L2 fuerte y **leave-one-out CV** (un holdout fijo
  sería puro ruido a este tamaño).
- **Un baseline que llevaba tres meses roto.** El script del Gemini genérico
  pedía `max_output_tokens=5`; como `gemini-2.5-flash` razona antes de responder,
  agotaba el presupuesto pensando y devolvía vacío. Un `except` silencioso
  convertía cada respuesta ilegible en un "2", así que **las 187 predicciones
  eran la misma constante** y el rival de la tesis no existía. Se detectó mirando
  el reparto de sus respuestas, no el error. Arreglado, el script ahora cuenta
  las respuestas ilegibles y avisa en voz alta si el baseline contesta siempre lo
  mismo. (Lección: una métrica que sale bien no es una métrica verificada.)
- **Comparar de forma justa.** Un LLM al que se le pregunta "¿le gustaría esto a
  un lector general?" contesta otra pregunta distinta a la del modelo. El rival
  honesto recibe **los mismos datos de entrenamiento** —40 poemas ya calificados,
  dentro del prompt— y se mide sobre **el mismo set de test**.
- **Evaluación honesta.** Se compara siempre contra un piso (clase mayoritaria)
  y contra el Gemini genérico, en accuracy *y* F1-macro (la métrica justa con
  clases desbalanceadas).

## Resultados

### El duelo: mismas cartas para los dos

Con **40 poemas de entrenamiento** y **147 de test**, idénticos para todos los
contendientes (3 clases: *no me gusta* / *medio* / *me gusta*):

| Contendiente | Accuracy | F1-macro |
|---|---:|---:|
| **Modelo personalizado** (embedding + forma) | 0.456 | **0.410** |
| Gemini con mis 40 poemas calificados en el prompt | 0.354 | 0.340 |
| Gemini genérico | 0.313 | 0.280 |
| Piso (clase mayoritaria) | 0.456 | 0.209 |

El clasificador gana **1.2×** al LLM que vio mis notas y **1.46×** al genérico.
Entrenado con sólo 40 poemas alcanza casi lo mismo que con 186 (0.410 vs 0.424):
la mayor parte de la señal del gusto está en las primeras decenas de ejemplos.

**Por qué pierde el LLM, que es lo interesante.** El Gemini genérico dice "me
gusta" al 71% del corpus; yo, al 24%. Preguntar por un lector general produce un
crítico complaciente. Al meterle mis notas en el prompt deja de serlo, pero
responde "medio" 85 de 147 veces: aprendió *que soy duro de contentar*, no *qué
me gusta*. De los 67 poemas que rechazo sólo identifica 17. **Cuarenta ejemplos
en un prompt transmiten la severidad, no el criterio** — y ese hueco es el que
llena un clasificador entrenado sobre embeddings.

*Nota honesta: en accuracy el modelo empata con el piso. Toda su ventaja está en
F1-macro, es decir, en distinguir las tres clases en lugar de responder siempre
"no me gusta". Con clases desbalanceadas esa es la métrica que importa.*

### La curva de aprendizaje

`data/historial.csv` registra una foto cada vez que crece el corpus (F1-macro,
3 clases, leave-one-out CV):

| Corpus | Forma (features) | Embedding | Gemini genérico |
|---|---:|---:|---:|
| 50 poemas (jun) | **0.399** | 0.244 | 0.237 |
| 187 poemas (sep) | 0.349 | **0.424** | 0.284 |

**El hallazgo con más recorrido del proyecto:** a n=50 el embedding sobreajustaba
y la señal venía de las features de forma; a n=187 se invirtió por completo. El
embedding casi dobla su F1 y las features de forma caen por debajo del piso. La
arquitectura no cambió — cambió la cantidad de datos. Es exactamente la razón de
ser del bucle de reentrenamiento con compuerta campeón–challenger: *cuál* modelo
es el mejor no es una decisión que se tome una vez.

(Las cifras de Gemini de ambas filas están re-medidas tras arreglar el baseline;
la columna `comentario` del CSV lo deja anotado.)

---|---:|---:|
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
