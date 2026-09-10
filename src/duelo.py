#!/usr/bin/env python3
"""El duelo: mi clasificador vs Gemini, con las mismas cartas.

La tesis del proyecto es "un modelo entrenado con MIS notas le gana a un LLM
genérico prediciendo MI gusto". Para que eso signifique algo, los dos rivales
tienen que jugar el mismo juego:

    - mismos datos de entrenamiento  → los 40 poemas de ejemplo del split
      (mi clasificador se entrena con ellos; Gemini los recibe en el prompt)
    - mismo set de test              → los 147 restantes
    - misma métrica                  → accuracy y F1-macro a 3 clases

Contendientes:
    mío (emb)        regresión logística sobre el embedding, entrenada con los 40
    mío (feat)       ídem sobre las features deterministas
    mío (emb+feat)   ídem sobre ambos
    gemini fewshot   Gemini con los 40 ejemplos calificados dentro del prompt
    gemini general   Gemini opinando como "lector general", sin saber nada de mí
    piso             predecir siempre la clase mayoritaria de los 40 ejemplos

Ojo con la lectura: el número de LOO-CV de src/train.py NO es comparable con
estos — aquel entrena con 186 poemas y este con 40. Aquí lo que importa es la
comparación entre columnas, no contra la corrida de train.py.

Uso:
    python src/duelo.py
"""
import csv
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train import cargar_datos, modelo_logistico, CLASES, ETIQUETAS  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SPLIT = RAIZ / "data" / "split_fewshot.csv"
FEWSHOT = RAIZ / "data" / "gemini_fewshot.csv"
GENERAL = RAIZ / "data" / "gemini_baseline.csv"


def marcador(nombre, y_true, y_pred, nota=""):
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    print(f"  {nombre:18} acc={acc:.3f}   F1={f1:.3f}   {nota}")
    return acc, f1


def leer_pred(ruta):
    return {r["id"]: int(r["pred"]) for r in csv.DictReader(ruta.open(encoding="utf-8"))}


def main():
    if not SPLIT.exists():
        sys.exit("Falta el split. Corre src/gemini_baseline.py --modo fewshot.")

    ids, emb, feat, y = cargar_datos()
    fila = {i: n for n, i in enumerate(ids)}
    rol = {r["id"]: r["rol"] for r in csv.DictReader(SPLIT.open(encoding="utf-8"))}

    tr = [fila[i] for i in ids if rol.get(i) == "ejemplo"]
    te = [fila[i] for i in ids if rol.get(i) == "test"]
    ids_te = [ids[n] for n in te]
    y_tr, y_te = y[tr], y[te]

    print(f"Entrenamiento: {len(tr)} poemas · Test: {len(te)} poemas")
    print(f"Notas en test: {dict((c, int((y_te == c).sum())) for c in CLASES)}")
    print(f"\n=== 3 CLASES · mismos datos, mismo test ===")

    conjuntos = {
        "mío (emb)": emb,
        "mío (feat)": feat,
        "mío (emb+feat)": np.hstack([emb, feat]),
    }
    resultados, preds = {}, {}
    for nombre, X in conjuntos.items():
        m = modelo_logistico().fit(X[tr], y_tr)
        preds[nombre] = m.predict(X[te])
        resultados[nombre] = marcador(nombre, y_te, preds[nombre])

    for nombre, ruta, nota in [
        ("gemini fewshot", FEWSHOT, "(los mismos 40 ejemplos, en el prompt)"),
        ("gemini general", GENERAL, "(sin saber nada de mí)"),
    ]:
        if not ruta.exists():
            print(f"  {nombre:18} (falta {ruta.name})")
            continue
        p = leer_pred(ruta)
        faltan = [i for i in ids_te if i not in p]
        if faltan:
            print(f"  {nombre:18} ⚠ sólo cubre {len(ids_te)-len(faltan)}/{len(ids_te)}; lo omito")
            continue
        preds[nombre] = np.array([p[i] for i in ids_te])
        resultados[nombre] = marcador(nombre, y_te, preds[nombre], nota)
        reparto = {c: int((preds[nombre] == c).sum()) for c in CLASES}
        print(f"  {'':18} reparto de sus respuestas: {reparto}")

    mayoritaria = int(np.bincount(y_tr).argmax())
    marcador("piso", y_te, np.full(len(y_te), mayoritaria),
             f"(decir siempre {mayoritaria} = '{ETIQUETAS[mayoritaria]}')")

    ganador = max(resultados, key=lambda k: resultados[k][1])
    print(f"\n  → gana en F1-macro: {ganador} ({resultados[ganador][1]:.3f})")

    if "gemini fewshot" in preds:
        print("\n  matriz de confusión — gemini fewshot:")
        cm = confusion_matrix(y_te, preds["gemini fewshot"], labels=CLASES)
        print("          " + " ".join(f"pred{c}" for c in CLASES))
        for i, c in enumerate(CLASES):
            print(f"    real{c} " + " ".join(f"{cm[i][j]:>5}" for j in range(3))
                  + f"   ({ETIQUETAS[c]})")


if __name__ == "__main__":
    main()
