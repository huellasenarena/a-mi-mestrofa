#!/usr/bin/env python3
"""Registra una foto del rendimiento del modelo HOY → data/historial.csv.

Cada fila es un punto de la curva de aprendizaje: cómo predice el modelo con
el corpus que hay en este momento. Corriéndolo cada vez que crece el corpus,
el CSV acumula la historia "mira al modelo aprender" que dibuja el sitio.

Mide sobre la tarea de 3 clases (la demo), con LOO-CV, tres conjuntos de
features (feat / emb / emb+feat) para ver CUÁNDO el embedding empieza a
aportar, más el baseline de Gemini genérico si está calculado.

Uso:
    python src/snapshot.py
"""
import csv
import sys
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.metrics import accuracy_score, f1_score

# Reutiliza la carga de datos y el modelo de train.py (una sola fuente de verdad).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train import cargar_datos, modelo_logistico, GEMINI  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
HIST = RAIZ / "data" / "historial.csv"

COLUMNAS = [
    "fecha", "n_poemas",
    "acc_feat", "f1_feat",       # solo features deterministas (forma)
    "acc_emb", "f1_emb",         # solo embedding (tema/tono)
    "acc_embfeat", "f1_embfeat", # ambos
    "acc_gemini", "f1_gemini",   # baseline Gemini genérico
]


def cv(X, y):
    yp = cross_val_predict(modelo_logistico(), X, y, cv=LeaveOneOut())
    return round(accuracy_score(y, yp), 3), round(
        f1_score(y, yp, average="macro", zero_division=0), 3
    )


def main():
    ids, emb, feat, y = cargar_datos()
    fila = {"fecha": date.today().isoformat(), "n_poemas": len(y)}

    for nombre, X in [("feat", feat), ("emb", emb),
                      ("embfeat", np.hstack([emb, feat]))]:
        acc, f1 = cv(X, y)
        fila[f"acc_{nombre}"] = acc
        fila[f"f1_{nombre}"] = f1

    if GEMINI.exists():
        pred = {r["id"]: int(r["pred"]) for r in csv.DictReader(GEMINI.open())}
        yg = np.array([pred[i] for i in ids])
        fila["acc_gemini"] = round(accuracy_score(y, yg), 3)
        fila["f1_gemini"] = round(f1_score(y, yg, average="macro", zero_division=0), 3)
    else:
        fila["acc_gemini"] = ""
        fila["f1_gemini"] = ""

    nuevo = not HIST.exists()
    with HIST.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        if nuevo:
            w.writeheader()
        w.writerow(fila)

    print(f"✓ Foto registrada en {HIST.relative_to(RAIZ)}  (n={len(y)} poemas)")
    print(f"  feat:  acc={fila['acc_feat']}  F1={fila['f1_feat']}")
    print(f"  emb:   acc={fila['acc_emb']}  F1={fila['f1_emb']}")
    print(f"  gemini:acc={fila['acc_gemini']}  F1={fila['f1_gemini']}")


if __name__ == "__main__":
    main()
