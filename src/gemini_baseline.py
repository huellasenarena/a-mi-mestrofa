#!/usr/bin/env python3
"""Baseline: un Gemini genérico predice la nota de cada poema.

Es el rival de la tesis: un LLM potente pero genérico, que NO conoce mi gusto,
contra mi clasificador entrenado con mis notas. El único trabajo del LLM aquí
es dar su opinión (ver CLAUDE.md) — no extrae features.

Predice sobre los 50 poemas y guarda data/gemini_baseline.csv (id, pred).
train.py lo lee para comparar. Se calcula una vez (cachea); --force recalcula.

Costo: ~50 generaciones cortas con gemini-2.5-flash. Céntimos, una sola vez.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "data" / "poemas.csv"
SALIDA = RAIZ / "data" / "gemini_baseline.csv"

PROYECTO = "a-mi-mestrofa"
REGION = "us-central1"
MODELO = "gemini-2.5-flash"

PROMPT = """Eres un lector de poesía. Te doy un poema en español y debes predecir
cuánto le gustaría a un lector general, en esta escala:
  1 = no me gusta
  2 = medio
  3 = me gusta
Responde ÚNICAMENTE con el dígito 1, 2 o 3. Sin explicación.

Poema:
\"\"\"
{texto}
\"\"\""""


def predecir(client, texto):
    r = client.models.generate_content(
        model=MODELO,
        contents=PROMPT.format(texto=texto[:6000]),
        config=GenerateContentConfig(temperature=0, max_output_tokens=5),
    )
    m = re.search(r"[123]", r.text or "")
    if not m:
        # respuesta inesperada: cae a 'medio' para no romper la alineación.
        return 2
    return int(m.group())


def main():
    ap = argparse.ArgumentParser(description="Baseline de Gemini genérico")
    ap.add_argument("--force", action="store_true", help="recalcula aunque exista")
    args = ap.parse_args()

    if SALIDA.exists() and not args.force:
        sys.exit(f"Ya existe {SALIDA.name}. Usa --force para recalcular.")
    if not ENTRADA.exists():
        sys.exit(f"No encuentro {ENTRADA}. Corre primero src/parse_seed.py.")

    poemas = list(csv.DictReader(ENTRADA.open(encoding="utf-8")))
    client = genai.Client(vertexai=True, project=PROYECTO, location=REGION)

    filas = []
    for r in poemas:
        pred = predecir(client, r["texto"])
        filas.append((r["id"], pred, r["nota"]))
        ok = "✓" if str(pred) == r["nota"] else " "
        print(f"  #{r['id']:>2}  gemini={pred}  real={r['nota']}  {ok}")

    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "pred", "nota"])
        w.writerows(filas)

    aciertos = sum(1 for _, p, n in filas if str(p) == n)
    print(f"\n✓ {len(filas)} predicciones → {SALIDA.relative_to(RAIZ)}")
    print(f"  accuracy cruda de Gemini genérico: {aciertos/len(filas):.3f}")


if __name__ == "__main__":
    main()
