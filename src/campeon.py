#!/usr/bin/env python3
"""Entrena el modelo campeón con todo el corpus y lo guarda para servirlo.

src/train.py mide; este script produce el archivo que usa el servidor de la
página "A mí me strofa" (servidor/). Mismo clasificador (modelo_logistico), mismo
criterio para elegir las features: el conjunto con mejor F1-macro en LOO-CV.

El archivo guarda, además del modelo, con qué se entrenó:
    - las claves `qmp:FECHA` de los poemas venidos del blog
    - una huella (sha256 del texto normalizado) de CADA poema del corpus
El servidor las usa para negarse a predecir un poema que el modelo ya vio: esa
predicción no sería fuera de muestra y ensuciaría el marcador público.

Compuerta campeón–challenger (CLAUDE.md): este script NO reemplaza a un campeón
existente. El primero entra sin rival porque no hay contra quién compararlo; los
siguientes sólo entran por src/compuerta.py.

Uso:
    python src/campeon.py
Salida:
    modelos/campeon.joblib   (fuera de git; se sube a GCS al desplegar)
"""
import csv
import hashlib
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import embeddings as emb_cfg  # noqa: E402
from train import FEAT_COLS, cargar_datos, evaluar, modelo_logistico  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "data" / "poemas.csv"
SALIDA = RAIZ / "modelos" / "campeon.joblib"


def huella(texto):
    """sha256 del texto sin mayúsculas, tildes, puntuación ni espacios extra.

    Así un mismo poema con otra maquetación (sangrías, saltos, comillas) da la
    misma huella. La usa también el servidor: tienen que coincidir.
    """
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if c.isalnum() or c.isspace())
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def conjuntos(emb, feat):
    return {"emb": emb, "feat": feat, "emb+feat": np.hstack([emb, feat])}


def cargar_todo():
    """(ids, emb, feat, y, corpus) — y comprueba que nada del corpus quede sin embeber."""
    ids, emb, feat, y = cargar_datos()
    corpus = list(csv.DictReader(CORPUS.open(encoding="utf-8")))
    faltan = {r["id"] for r in corpus} - set(ids)
    if faltan:
        sys.exit(f"{len(faltan)} poemas del corpus sin embedding/features "
                 f"(ids {sorted(faltan, key=int)[:10]}). Corre src/embeddings.py y src/features.py.")
    return ids, emb, feat, y, corpus


def crear_artefacto(X, y, conjunto, f1, corpus):
    """Entrena con TODO el corpus y arma el archivo que sirve el servidor."""
    modelo = modelo_logistico().fit(X, y)
    if list(modelo.classes_) != [1, 2, 3]:
        sys.exit(f"Clases inesperadas: {modelo.classes_}")
    ahora = datetime.now(timezone.utc)
    return {
        "version": f"{ahora:%Y-%m-%d}-n{len(y)}-{conjunto}",
        "entrenado_el": ahora.isoformat(timespec="seconds"),
        "modelo": modelo,
        "conjunto": conjunto,
        "feat_cols": FEAT_COLS,
        "f1_loo": round(f1, 3),
        "n": len(y),
        "embedding": {
            "modelo": emb_cfg.MODELO,
            "dimension": emb_cfg.DIMENSION,
            "max_chars": emb_cfg.MAX_CHARS,
        },
        "claves_qmp": sorted({(r.get("fuente") or "").strip() for r in corpus} - {""}),
        "huellas": sorted({huella(r["texto"]) for r in corpus}),
    }


def main():
    if SALIDA.exists():
        sys.exit(f"Ya hay un campeón en {SALIDA.relative_to(RAIZ)}. No lo reemplazo "
                 "sin compuerta: usa src/compuerta.py (ver CLAUDE.md).")

    ids, emb, feat, y, corpus = cargar_todo()
    print(f"Corpus: {len(y)} poemas. Eligiendo features por F1-macro (LOO-CV):")
    candidatos = conjuntos(emb, feat)
    f1 = {nombre: evaluar(nombre, X, y)[1] for nombre, X in candidatos.items()}
    elegido = max(f1, key=f1.get)

    artefacto = crear_artefacto(candidatos[elegido], y, elegido, f1[elegido], corpus)
    SALIDA.parent.mkdir(exist_ok=True)
    joblib.dump(artefacto, SALIDA)
    print(f"\n✓ campeón {artefacto['version']} (F1 LOO {f1[elegido]:.3f}) → {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
