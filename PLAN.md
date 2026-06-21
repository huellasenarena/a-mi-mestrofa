# Plan de construcción — "¿Me gustará este poema?"

**Proyecto de IA en Vertex AI · Semanas 1–2**

**Objetivo:** un predictor personalizado de poesía que aprende tu gusto y lo demuestra contra un Gemini genérico — pieza de portafolio + práctica directa de los dominios pesados del PMLE.

**Principio rector:** rebanada vertical primero. La Semana 1 hace que la idea *funcione de punta a punta* con lo mínimo; la Semana 2 la convierte en producto y le añade la maquinaria MLOps. Si algo se cae, nunca es el demo que funciona.

*Fechas ancladas a lunes 23 jun; muévelas si arrancas este fin de semana. Buffer hasta el ~12 jul (portafolio en vivo).*

---

## Semana 1 — Que funcione de punta a punta
**Lun 23 – Dom 29 jun · ~22–26 h**

### Bloque A · Cimientos GCP (~3 h)
- [ ] Crear / confirmar el proyecto en Google Cloud
- [ ] Activar facturación + APIs (Vertex AI, BigQuery)
- [ ] Configurar `gcloud` y la autenticación local
- [ ] Poner una alerta de presupuesto (p. ej. $20) — higiene de costos desde el día 1

### Bloque B · Datos semilla — arranque por lotes (~6–8 h) ⟵ la pieza más larga, va primero
- [ ] Reunir 60–100 poemas: archivo de Qué Mal Poema + poemas que **amas** y poemas que **detestas**
- [ ] Captura mínima de calificación (un CSV o un script simple; el sitio bonito viene después)
- [ ] Calificar todos: `mal` / `medio` / `me gusta`

### Bloque C · Features + embeddings (~4–5 h)
- [ ] Script de features deterministas con código (estrofas, nº de versos, longitud media, diversidad léxica, densidad de puntuación)
- [ ] Llamar a `gemini-embedding-001` por poema y guardar los vectores

### Bloque D · Primer modelo (~5–6 h)
- [ ] Notebook: entrenar un clasificador ligero (regresión logística) sobre embedding + features
- [ ] Evaluar: accuracy + F1 por clase + matriz de confusión
- [ ] Baseline: ¿le gana a un Gemini genérico sobre el mismo set?

> **Hito (Dom 29 jun):** pego un poema y recibo una predicción entrenada con *mis* notas, con una cifra que prueba que funciona. ✅ Tesis validada — y si la cifra es floja, aquí es barato ajustar antes de construir más.

---

## Semana 2 — De prototipo a producto
**Lun 30 jun – Dom 6 jul · ~24–28 h**

### Bloque E · Datos a BigQuery (~3 h)
- [ ] Esquema: poemas, notas, features, embeddings, predicciones
- [ ] Cargar los datos del notebook

### Bloque F · Servir el modelo (~4–5 h)
- [ ] Registrar el modelo en el Model Registry
- [ ] Desplegar: endpoint de Vertex AI **o** Cloud Run si quieres ahorrar (decide según el costo en reposo)
- [ ] Probar la predicción en vivo vía API

### Bloque G · La app de dos partes — centro de la demo (~8–10 h)
- [ ] Vista 1: calificar / etiquetar poemas
- [ ] Vista 2: leer → calificar → comparar (**tu nota** vs **Gemini genérico** vs **tu modelo**)
- [ ] Conectar al endpoint + escribir cada predicción y nota a BigQuery

### Bloque H · Bucle de reentrenamiento (~5–6 h) ⟵ válvula de seguridad si falta tiempo
- [ ] Vertex AI Pipeline: extrae → valida → entrena challenger → evalúa vs campeón → compuerta → despliega/conserva
- [ ] Disparo manual primero; programar con Cloud Scheduler si alcanza el tiempo

### Bloque I · Monitoreo + narrativa (~3–4 h)
- [ ] Registrar predicción-vs-nota real → gráfica de exactitud en el tiempo (tu modelo vs baseline)
- [ ] Borrador del relato: problema → solución → arquitectura → stack → retos → resultados

> **Hito (Dom 6 jul):** app en vivo + modelo desplegado + pipeline v1 + relato escrito. Listo para destacar cuando pulas el portafolio (~12 jul).

---

## Reglas del plan

- **Línea de corte (si una semana se aprieta):** la rebanada de la Semana 1 es intocable. En la Semana 2, la app en vivo con la comparación de tres notas manda. El **Bloque H** (bucle automático) es lo primero que se simplifica — un disparo manual, o incluso documentar "así correría" sin llegar a programarlo, es aceptable para el portafolio.
- **Regla de seguridad:** nunca recortes horas de certificación ni de aplicaciones para terminar esto. El portafolio cede primero.
- **Doble función:** todo el MLOps de la Semana 2 (pipeline, registry, serving, monitoreo) es práctica directa de los dominios más pesados del PMLE (~55% del examen).
