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

Modo incremental (por defecto): lee lo que ya hay en disco y sólo llama a la
API por los poemas que faltan. Es el modo normal de trabajo — el corpus crece
cada semana y re-embeber lo ya embebido es tirar dinero y contradecir la regla
de "una sola vez por poema". Los vectores existentes se reutilizan por id; la
nota se refresca desde poemas.csv por si la recalifiqué.

Salida:
    data/embeddings.npy        matriz float32 (n_poemas, 256), filas en orden de id
    data/embeddings_meta.csv   id, nota  — misma fila que la matriz

Uso:
    python src/embeddings.py            # embebe sólo los que falten
    python src/embeddings.py --force    # recalcula todo el corpus desde cero

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
# cada cuántos poemas nuevos se guarda a disco: si la corrida se cae a mitad,
# no se pierden las llamadas ya pagadas.
CADA = 25


def cargar_poemas():
    if not ENTRADA.exists():
        sys.exit(f"No encuentro {ENTRADA}. Corre primero src/parse_seed.py.")
    return list(csv.DictReader(ENTRADA.open(encoding="utf-8")))


def cargar_existentes():
    """Devuelve {id: vector} de lo ya embebido, o {} si no hay nada válido."""
    if not (SALIDA_NPY.exists() and SALIDA_META.exists()):
        return {}
    matriz = np.load(SALIDA_NPY)
    meta = list(csv.DictReader(SALIDA_META.open(encoding="utf-8")))
    if len(meta) != matriz.shape[0]:
        sys.exit(
            f"Desalineado: {SALIDA_META.name} tiene {len(meta)} filas y "
            f"{SALIDA_NPY.name} tiene {matriz.shape[0]}. Usa --force."
        )
    if matriz.shape[1] != DIMENSION:
        sys.exit(
            f"{SALIDA_NPY.name} tiene dim {matriz.shape[1]} ≠ {DIMENSION} "
            "(¿cambió la configuración?). Usa --force."
        )
    return {m["id"]: matriz[i] for i, m in enumerate(meta)}


def embeber(client, texto):
    resp = client.models.embed_content(
        model=MODELO,
        contents=[texto[:MAX_CHARS]],
        config=EmbedContentConfig(
            output_dimensionality=DIMENSION, task_type="CLASSIFICATION"
        ),
    )
    return resp.embeddings[0].values


def guardar(poemas, vectores):
    """Escribe matriz + meta en el orden de poemas.csv, sólo con lo embebido."""
    listos = [r for r in poemas if r["id"] in vectores]
    matriz = np.asarray([vectores[r["id"]] for r in listos], dtype=np.float32)
    np.save(SALIDA_NPY, matriz)
    with SALIDA_META.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "nota"])
        w.writerows((r["id"], r["nota"]) for r in listos)
    return matriz


def main():
    ap = argparse.ArgumentParser(description="Embebe el corpus con gemini-embedding-001")
    ap.add_argument("--force", action="store_true",
                    help="recalcula todo el corpus, ignorando lo ya embebido")
    args = ap.parse_args()

    poemas = cargar_poemas()
    vectores = {} if args.force else cargar_existentes()
    faltan = [r for r in poemas if r["id"] not in vectores]

    # los ids guardados que ya no están en poemas.csv no se arrastran: guardar()
    # reconstruye la matriz sólo con las filas del corpus actual.
    reusados = len({r["id"] for r in poemas} & set(vectores))
    print(f"Corpus: {len(poemas)} poemas · reuso {reusados} embeddings · faltan {len(faltan)}")

    if not faltan:
        matriz = guardar(poemas, vectores)
        print(f"✓ Nada que embeber. {matriz.shape[0]} vectores de dim {matriz.shape[1]}.")
        return

    client = genai.Client(vertexai=True, project=PROYECTO, location=REGION)
    for n, r in enumerate(faltan, 1):
        v = embeber(client, r["texto"])
        if len(v) != DIMENSION:
            guardar(poemas, vectores)
            sys.exit(f"Poema {r['id']}: dim {len(v)} ≠ {DIMENSION}. Aborto (guardé lo anterior).")
        vectores[r["id"]] = np.asarray(v, dtype=np.float32)
        print(f"  embebido #{r['id']:>3}  (nota {r['nota']})  [{n}/{len(faltan)}]")
        if n % CADA == 0:
            guardar(poemas, vectores)
            print(f"  … guardado parcial ({n}/{len(faltan)})")

    matriz = guardar(poemas, vectores)
    print(f"\n✓ {matriz.shape[0]} embeddings de dim {matriz.shape[1]} "
          f"→ {SALIDA_NPY.relative_to(RAIZ)}  ({len(faltan)} nuevos)")
    print(f"  meta alineada → {SALIDA_META.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
