#!/usr/bin/env python3
"""Entrena y evalúa el clasificador personalizado de gusto poético.

Combina (o compara por separado):
    - embedding del poema (gemini-embedding-001, 256 dims) → tema/tono
    - features deterministas (5) → forma
en un clasificador ligero (regresión logística).

Evaluación honesta para n=50: leave-one-out CV (con 50 muestras, un holdout
sería ruido; LOO usa cada poema de test una vez). Reporta accuracy y F1-macro
contra el piso de clase mayoritaria, para dos tareas:
    - 3 clases  (la demo: no me gusta / medio / me gusta)
    - binaria   (me gusta vs no me gusta, descartando 'medio' — la señal limpia)
y para tres conjuntos de features (emb / feat / emb+feat), para ver QUÉ aporta.

Hallazgo a n=50: las features deterministas (forma) llevan la señal; el
embedding sobreajusta por su alta dimensión y aún no aporta. Debería cambiar
al crecer el corpus — por eso el bucle de reentrenamiento.

El baseline de Gemini genérico vive aparte (src/gemini_baseline.py) porque
cuesta llamadas a un LLM; este script lo lee si existe.
"""
import csv
import sys
from pathlib import Path

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parent.parent
EMB_NPY = RAIZ / "data" / "embeddings.npy"
EMB_META = RAIZ / "data" / "embeddings_meta.csv"
FEATURES = RAIZ / "data" / "features.csv"
GEMINI = RAIZ / "data" / "gemini_baseline.csv"

CLASES = [1, 2, 3]
ETIQUETAS = {1: "no me gusta", 2: "medio", 3: "me gusta"}
FEAT_COLS = [
    "n_versos",
    "n_estrofas",
    "long_media_verso",
    "diversidad_lexica",
    "densidad_puntuacion",
]


def cargar_datos():
    """Devuelve (ids, emb, feat, y) alineados por id."""
    if not EMB_NPY.exists():
        sys.exit("Faltan embeddings. Corre src/embeddings.py.")
    if not FEATURES.exists():
        sys.exit("Faltan features. Corre src/features.py.")

    emb = np.load(EMB_NPY)
    meta = list(csv.DictReader(EMB_META.open(encoding="utf-8")))
    feats = {r["id"]: r for r in csv.DictReader(FEATURES.open(encoding="utf-8"))}

    ids = [m["id"] for m in meta]
    y = np.array([int(m["nota"]) for m in meta])
    feat = np.array([[float(feats[i][c]) for c in FEAT_COLS] for i in ids],
                    dtype=np.float32)
    return ids, emb.astype(np.float32), feat, y


def modelo_logistico():
    """Escalado + logística con L2 fuerte (C=0.1) y clases balanceadas."""
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.1, max_iter=3000, class_weight="balanced"),
    )


def evaluar(nombre, X, y):
    """LOO-CV; devuelve (acc, f1, y_pred)."""
    y_pred = cross_val_predict(modelo_logistico(), X, y, cv=LeaveOneOut())
    acc = accuracy_score(y, y_pred)
    f1 = f1_score(y, y_pred, average="macro", zero_division=0)
    print(f"    {nombre:14} acc={acc:.3f}  F1={f1:.3f}")
    return acc, f1, y_pred


def piso(y):
    return max(np.bincount(y)) / len(y)


def tarea(titulo, emb, feat, y):
    print(f"\n=== {titulo} · piso(clase mayoritaria)={piso(y):.3f} ===")
    conjuntos = {
        "emb": emb,
        "feat": feat,
        "emb+feat": np.hstack([emb, feat]),
    }
    resultados = {}
    for nombre, X in conjuntos.items():
        resultados[nombre] = evaluar(nombre, X, y)
    return resultados


def main():
    ids, emb, feat, y = cargar_datos()
    dist = {c: int((y == c).sum()) for c in CLASES}
    print(f"Dataset: {len(y)} poemas · {emb.shape[1]} dims emb + "
          f"{feat.shape[1]} features deterministas")
    print(f"Distribución de notas: {dist}")

    # Tarea 1 — la demo de 3 clases.
    r3 = tarea("3 CLASES (no me gusta / medio / me gusta)", emb, feat, y)
    print("\n    matriz de confusión (mejor conjunto = feat):")
    _, _, yp = r3["feat"]
    cm = confusion_matrix(y, yp, labels=CLASES)
    print("            " + " ".join(f"pred{c}" for c in CLASES))
    for i, c in enumerate(CLASES):
        print(f"      real{c}  " + " ".join(f"{cm[i][j]:>5}" for j in range(3))
              + f"   ({ETIQUETAS[c]})")

    # Tarea 2 — señal binaria limpia: me gusta vs no me gusta (sin 'medio').
    mask = (y == 1) | (y == 3)
    yb = (y[mask] == 3).astype(int)
    tarea("BINARIA me gusta(3) vs no me gusta(1)", emb[mask], feat[mask], yb)

    # Baseline Gemini genérico (3 clases), si ya se calculó.
    print("\n=== Baseline Gemini genérico (3 clases) ===")
    if GEMINI.exists():
        pred = {r["id"]: int(r["pred"]) for r in csv.DictReader(GEMINI.open())}
        y_gem = np.array([pred[i] for i in ids])
        acc = accuracy_score(y, y_gem)
        f1 = f1_score(y, y_gem, average="macro", zero_division=0)
        print(f"    gemini         acc={acc:.3f}  F1={f1:.3f}")
    else:
        print("    (aún no calculado — corre src/gemini_baseline.py)")


if __name__ == "__main__":
    main()
