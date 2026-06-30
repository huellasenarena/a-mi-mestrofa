#!/usr/bin/env python3
"""Embebe cada poema una sola vez con gemini-embedding-001 (Vertex AI).

Por qué así (ver CLAUDE.md):
- El embedding captura tema/tono; las features deterministas capturan la forma.
- Se calcula UNA vez por poema y se guarda. Nunca se re-embebe en entrenamiento.
- Dimensión reducida a 256: con ~50 poemas, 3072 dims (el default) garantizan
  sobreajuste. 256 ya es mucho para n=50, pero el truncado nativo del modelo
  conserva la señal principal; la regularización del clasificador hace el resto.
- task_type=CLASSIFICATION: le dice al modelo que el vector se usará para
  clasificar, no para búsqueda semántica.

Salida:
    data/embeddings.npy        matriz float32 (n_poemas, 256), filas en orden de id
    data/embeddings_meta.csv   id, nota  — misma fila que la matriz

Uso:
    python src/embeddings.py            # embebe si falta (no recalcula)
    python src/embeddings.py --force    # recalcula todo

Costo: una fracción de céntimo por el corpus completo. No es costo en reposo.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from google import genai
from google.genai.types import EmbedContentConfig

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "data" / "poemas.csv"
SALIDA_NPY = RAIZ / "data" / "embeddings.npy"
SALIDA_META = RAIZ / "data" / "embeddings_meta.csv"

PROYECTO = "a-mi-mestrofa"
REGION = "us-central1"
MODELO = "gemini-embedding-001"
DIMENSION = 256
# gemini-embedding-001 admite ~2048 tokens; recortamos por seguridad los poemas
# muy largos (≈ 8000 chars ~ 2000 tokens en español). Solo afecta a 1-2 poemas.
MAX_CHARS = 8000


def cargar_poemas():
    if not ENTRADA.exists():
        sys.exit(f"No encuentro {ENTRADA}. Corre primero src/parse_seed.py.")
    return list(csv.DictReader(ENTRADA.open(encoding="utf-8")))


def embeber(client, texto):
    resp = client.models.embed_content(
        model=MODELO,
        contents=[texto[:MAX_CHARS]],
        config=EmbedContentConfig(
            output_dimensionality=DIMENSION, task_type="CLASSIFICATION"
        ),
    )
    return resp.embeddings[0].values


def main():
    ap = argparse.ArgumentParser(description="Embebe el corpus con gemini-embedding-001")
    ap.add_argument("--force", action="store_true", help="recalcula aunque ya exista")
    args = ap.parse_args()

    if SALIDA_NPY.exists() and not args.force:
        sys.exit(
            f"Ya existe {SALIDA_NPY.name}. Usa --force para recalcular "
            "(recuerda: los embeddings se calculan una sola vez)."
        )

    poemas = cargar_poemas()
    client = genai.Client(vertexai=True, project=PROYECTO, location=REGION)

    vectores, meta = [], []
    for r in poemas:
        v = embeber(client, r["texto"])
        if len(v) != DIMENSION:
            sys.exit(f"Poema {r['id']}: dim {len(v)} ≠ {DIMENSION}. Aborto.")
        vectores.append(v)
        meta.append((r["id"], r["nota"]))
        print(f"  embebido #{r['id']:>2}  (nota {r['nota']})")

    matriz = np.asarray(vectores, dtype=np.float32)
    np.save(SALIDA_NPY, matriz)
    with SALIDA_META.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "nota"])
        w.writerows(meta)

    print(f"\n✓ {matriz.shape[0]} embeddings de dim {matriz.shape[1]} "
          f"→ {SALIDA_NPY.relative_to(RAIZ)}")
    print(f"  meta alineada → {SALIDA_META.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
