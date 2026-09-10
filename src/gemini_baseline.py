#!/usr/bin/env python3
"""Baselines de Gemini: el rival de la tesis del proyecto.

Dos modos, dos rivales distintos:

  --modo general   (B1) Gemini opina como "lector general", sin saber nada de mí.
                   Es el rival débil: contesta una pregunta distinta a la de mi
                   modelo (gusto general vs MI gusto). Sirve de piso.

  --modo fewshot   (B3) Gemini recibe N poemas ya calificados POR MÍ dentro del
                   prompt y predice el resto. Es el rival de verdad: un LLM con
                   acceso a los mismos datos de entrenamiento, en contexto. Si
                   mi clasificador le gana a esto, la tesis está probada.

El único trabajo del LLM aquí es dar su opinión (ver CLAUDE.md) — no extrae
features.

Split (modo fewshot): los N poemas de ejemplo se apartan y NO se predicen —
predecir un poema que está en su propio prompt sería fuga. El split se guarda
en data/split_fewshot.csv para que src/duelo.py entrene el clasificador con
exactamente los mismos ejemplos y evalúe sobre exactamente el mismo test.

Bug histórico (corregido el 10 sep 2026): con max_output_tokens=5, gemini-2.5-flash
—que razona antes de responder— agotaba el presupuesto pensando y devolvía
vacío. La regex fallaba y el fallback silencioso devolvía "2", así que TODAS las
predicciones eran 2 y el baseline llevaba roto desde junio. Ahora el presupuesto
deja terminar el razonamiento y las respuestas ilegibles se cuentan y se avisan
en voz alta en vez de disfrazarse de predicción.

Uso:
    python src/gemini_baseline.py --modo general
    python src/gemini_baseline.py --modo fewshot --ejemplos 40

Costo: céntimos por corrida (gemini-2.5-flash, generaciones de un dígito).
El modo fewshot manda los ejemplos en cada llamada: con 40 ejemplos son
~6k tokens de entrada por poema, del orden de $0.3 por corrida completa.
"""
import argparse
import csv
import random
import re
import sys
from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "data" / "poemas.csv"
SALIDA_GENERAL = RAIZ / "data" / "gemini_baseline.csv"
SALIDA_FEWSHOT = RAIZ / "data" / "gemini_fewshot.csv"
SPLIT = RAIZ / "data" / "split_fewshot.csv"

PROYECTO = "a-mi-mestrofa"
REGION = "us-central1"
MODELO = "gemini-2.5-flash"
# suficiente para que el modelo razone Y escriba el dígito (ver bug arriba).
MAX_OUT = 512
MAX_CHARS_POEMA = 6000
# los poemas de ejemplo se recortan para acotar el tamaño (y el costo) del prompt.
MAX_CHARS_EJEMPLO = 1200

PROMPT_GENERAL = """Eres un lector de poesía. Te doy un poema en español y debes predecir
cuánto le gustaría a un lector general, en esta escala:
  1 = no me gusta
  2 = medio
  3 = me gusta
Responde ÚNICAMENTE con el dígito 1, 2 o 3. Sin explicación.

Poema:
\"\"\"
{texto}
\"\"\""""

PROMPT_FEWSHOT = """Una persona concreta califica poemas en español según su gusto personal:
  1 = no me gusta
  2 = medio
  3 = me gusta

Estos son poemas que ESA persona ya calificó:

{ejemplos}

Ahora predice qué nota le pondría ESA MISMA persona al siguiente poema.
No juzgues el poema por su calidad literaria general: deduce el gusto particular
que revelan los ejemplos y aplícalo.

Poema a predecir:
\"\"\"
{texto}
\"\"\"

Responde ÚNICAMENTE con el dígito 1, 2 o 3. Sin explicación."""


def cargar_poemas():
    if not ENTRADA.exists():
        sys.exit(f"No encuentro {ENTRADA}. Corre primero src/parse_seed.py.")
    return list(csv.DictReader(ENTRADA.open(encoding="utf-8")))


def elegir_ejemplos(poemas, n, semilla):
    """N poemas de ejemplo, estratificados por nota para no sesgar el prompt."""
    rng = random.Random(semilla)
    por_nota = {}
    for r in poemas:
        por_nota.setdefault(r["nota"], []).append(r)

    elegidos = []
    for nota, grupo in sorted(por_nota.items()):
        cuota = round(n * len(grupo) / len(poemas))
        elegidos += rng.sample(grupo, min(cuota, len(grupo)))
    # el redondeo por clase puede desviarse un poco de n; se ajusta al final.
    resto = [r for r in poemas if r not in elegidos]
    while len(elegidos) < n and resto:
        elegidos.append(resto.pop(rng.randrange(len(resto))))
    rng.shuffle(elegidos)
    return elegidos


def bloque_ejemplos(ejemplos):
    return "\n\n".join(
        f"--- Poema (nota {r['nota']}) ---\n{r['texto'][:MAX_CHARS_EJEMPLO]}"
        for r in ejemplos
    )


def predecir(client, prompt):
    """Devuelve (nota, ok). ok=False si la respuesta fue ilegible."""
    r = client.models.generate_content(
        model=MODELO,
        contents=prompt,
        config=GenerateContentConfig(temperature=0, max_output_tokens=MAX_OUT),
    )
    m = re.search(r"[123]", r.text or "")
    if not m:
        return 2, False
    return int(m.group()), True


def main():
    ap = argparse.ArgumentParser(description="Baselines de Gemini genérico")
    ap.add_argument("--modo", choices=("general", "fewshot"), required=True)
    ap.add_argument("--ejemplos", type=int, default=40,
                    help="poemas de ejemplo en el prompt (sólo --modo fewshot)")
    ap.add_argument("--semilla", type=int, default=0, help="semilla del split")
    ap.add_argument("--force", action="store_true", help="recalcula aunque exista")
    args = ap.parse_args()

    salida = SALIDA_GENERAL if args.modo == "general" else SALIDA_FEWSHOT
    if salida.exists() and not args.force:
        sys.exit(f"Ya existe {salida.name}. Usa --force para recalcular.")

    poemas = cargar_poemas()
    client = genai.Client(vertexai=True, project=PROYECTO, location=REGION)

    if args.modo == "general":
        objetivo, prefijo = poemas, None
    else:
        ejemplos = elegir_ejemplos(poemas, args.ejemplos, args.semilla)
        ids_ej = {r["id"] for r in ejemplos}
        objetivo = [r for r in poemas if r["id"] not in ids_ej]
        prefijo = bloque_ejemplos(ejemplos)
        with SPLIT.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "rol"])
            w.writerows((r["id"], "ejemplo" if r["id"] in ids_ej else "test")
                        for r in poemas)
        print(f"Split: {len(ids_ej)} ejemplos en el prompt, {len(objetivo)} a predecir "
              f"→ {SPLIT.relative_to(RAIZ)}")

    filas, ilegibles = [], []
    for n, r in enumerate(objetivo, 1):
        texto = r["texto"][:MAX_CHARS_POEMA]
        prompt = (PROMPT_GENERAL.format(texto=texto) if args.modo == "general"
                  else PROMPT_FEWSHOT.format(ejemplos=prefijo, texto=texto))
        pred, ok = predecir(client, prompt)
        if not ok:
            ilegibles.append(r["id"])
        filas.append((r["id"], pred, r["nota"]))
        marca = "✓" if str(pred) == r["nota"] else " "
        aviso = "" if ok else "  ⚠ respuesta ilegible → 2"
        print(f"  #{r['id']:>3}  gemini={pred}  real={r['nota']}  {marca}"
              f"  [{n}/{len(objetivo)}]{aviso}")

    with salida.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "pred", "nota"])
        w.writerows(filas)

    aciertos = sum(1 for _, p, nota in filas if str(p) == nota)
    reparto = {c: sum(1 for _, p, _ in filas if p == c) for c in (1, 2, 3)}
    print(f"\n✓ {len(filas)} predicciones → {salida.relative_to(RAIZ)}")
    print(f"  accuracy cruda: {aciertos/len(filas):.3f}")
    print(f"  reparto de sus predicciones: {reparto}")
    if ilegibles:
        print(f"  ⚠ {len(ilegibles)} respuestas ilegibles (no son opinión de Gemini, "
              f"son relleno): ids {ilegibles[:10]}")
    if len(set(p for _, p, _ in filas)) == 1:
        print("  ⚠ Gemini contestó SIEMPRE lo mismo: el baseline no está opinando.")


if __name__ == "__main__":
    main()
