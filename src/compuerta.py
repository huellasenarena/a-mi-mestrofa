#!/usr/bin/env python3
"""Compuerta campeón–challenger: ¿el modelo reentrenado es mejor que el de producción?

La regla de CLAUDE.md: un modelo nuevo sólo reemplaza al de producción si lo
supera. Para que "supera" signifique algo, los dos se examinan con los MISMOS
poemas y ninguno de los dos puede haberlos visto:

    el examen      los poemas del blog que predijo el campeón actual y que ya
                   están en el corpus con su nota
    el campeón     sus predicciones congeladas de esos días (las del marcador
                   público, leídas del servidor); las hizo antes de ver la nota
    el challenger  para cada poema del examen se entrena con TODO el corpus
                   menos ese poema, y lo predice
    Gemini         sus predicciones congeladas, como referencia
    la frecuente   para cada poema, la nota más común del resto del corpus: lo que
                   acierta quien no lee el poema. Un modelo que no la supera no
                   entiende el gusto, sólo aprendió qué nota pongo más

Qué features usa el challenger (emb / feat / emb+feat) se elige con LOO-CV sobre
los poemas que NO son del examen: elegirlas mirando el examen sería trampa.

Con pocos poemas, ganar o perder es azar, así que por debajo de --minimo (20)
enseña los números pero no decide nada. Sólo reemplaza si el challenger saca MÁS F1-macro; con empate
se queda el campeón. Cada corrida se anota en data/compuerta.csv, gane quien
gane.

No despliega: si gana el challenger, lo guarda en modelos/ y enseña los dos
comandos para publicarlo.

Uso:
    MESTROFA_SERVIDOR=https://… python src/compuerta.py
"""
import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import LeaveOneOut, cross_val_predict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campeon import cargar_todo, conjuntos, crear_artefacto  # noqa: E402
from importar_qmp import bajar  # noqa: E402
import train  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "data" / "compuerta.csv"
MODELOS = RAIZ / "modelos"
MINIMO = 20
CLASES = [1, 2, 3]
BUCKET = "gs://a-mi-mestrofa-modelos/campeon"


def _f1(y, p):
    return float(f1_score(y, p, labels=CLASES, average="macro", zero_division=0))


def _acc(y, p):
    return float(accuracy_score(y, p))


def examinar(candidatos, y, es_examen, pred_campeon, pred_gemini, minimo=MINIMO):
    """El corazón de la compuerta, sin archivos ni red.

    candidatos    {nombre: X} con una fila por poema del corpus
    y             notas reales
    es_examen     máscara booleana: qué poemas forman el examen
    pred_campeon  predicciones congeladas del campeón, en el orden del examen
    pred_gemini   ídem de Gemini
    """
    examen = np.flatnonzero(es_examen)
    res = {"n": len(examen)}
    if len(examen) == 0:
        return {**res, "decision": "faltan_datos"}

    # 1. Elegir features sin mirar el examen.
    fuera = ~es_examen
    f1_sel = {
        nombre: _f1(y[fuera], cross_val_predict(train.modelo_logistico(), X[fuera], y[fuera],
                                                cv=LeaveOneOut()))
        for nombre, X in candidatos.items()
    }
    conjunto = max(f1_sel, key=f1_sel.get)
    X = candidatos[conjunto]

    # 2. El challenger predice cada poema del examen sin haberlo visto.
    todos = np.arange(len(y))
    pred_challenger = np.array([
        train.modelo_logistico().fit(X[todos != i], y[todos != i]).predict(X[i:i + 1])[0]
        for i in examen
    ])

    # 3. La frecuente: con lo mismo que sabe el challenger, pero sin leer el poema.
    pred_frecuente = np.array([
        CLASES[int(np.argmax([np.sum(y[todos != i] == c) for c in CLASES]))]
        for i in examen
    ])

    y_ex = y[examen]
    res.update({
        "conjunto": conjunto,
        "f1_campeon": _f1(y_ex, pred_campeon), "acc_campeon": _acc(y_ex, pred_campeon),
        "f1_challenger": _f1(y_ex, pred_challenger), "acc_challenger": _acc(y_ex, pred_challenger),
        "f1_gemini": _f1(y_ex, pred_gemini), "acc_gemini": _acc(y_ex, pred_gemini),
        "f1_frecuente": _f1(y_ex, pred_frecuente), "acc_frecuente": _acc(y_ex, pred_frecuente),
    })
    if len(examen) < minimo:
        res["decision"] = "faltan_datos"
    else:
        res["decision"] = "cambiar" if res["f1_challenger"] > res["f1_campeon"] else "conservar"
    return res


def anotar(res, version_campeon):
    nuevo = not REGISTRO.exists()
    cols = ["fecha", "campeon", "n", "conjunto", "f1_campeon", "acc_campeon",
            "f1_challenger", "acc_challenger", "f1_gemini", "acc_gemini", "f1_frecuente", "acc_frecuente", "decision"]
    with REGISTRO.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if nuevo:
            w.writeheader()
        fila = {"fecha": date.today().isoformat(), "campeon": version_campeon}
        for c in cols[2:]:
            v = res.get(c, "")
            fila[c] = round(v, 3) if isinstance(v, float) else v
        w.writerow(fila)


def main():
    ap = argparse.ArgumentParser(description="Compuerta campeón–challenger")
    ap.add_argument("--servidor", default=os.environ.get("MESTROFA_SERVIDOR"),
                    help="URL del servidor de la página (o MESTROFA_SERVIDOR)")
    ap.add_argument("--minimo", type=int, default=MINIMO,
                    help=f"poemas del examen necesarios para decidir (por defecto {MINIMO})")
    args = ap.parse_args()
    if not args.servidor:
        sys.exit("Falta el servidor (--servidor o MESTROFA_SERVIDOR): de ahí salen "
                 "las predicciones congeladas del campeón.")

    predicciones = json.loads(bajar(f"{args.servidor.rstrip('/')}/predicciones"))
    if not predicciones:
        sys.exit("El servidor todavía no tiene ninguna predicción guardada.")
    # El campeón en producción es el que hizo la predicción más reciente.
    version = max(predicciones, key=lambda p: p["fecha"])["modelo_version"]
    del_campeon = {p["fecha"]: p for p in predicciones if p["modelo_version"] == version}

    ids, emb, feat, y, corpus = cargar_todo()
    fecha_de = {r["id"]: (r.get("fuente") or "").removeprefix("qmp:") for r in corpus}
    es_examen = np.array([fecha_de[i] in del_campeon for i in ids])
    fechas_examen = [fecha_de[i] for i, e in zip(ids, es_examen) if e]
    sin_importar = len(del_campeon) - len(fechas_examen)

    print(f"Campeón en producción: {version}")
    print(f"Examen: {len(fechas_examen)} poemas del blog "
          f"({sin_importar} predichos que aún no están en el corpus)")

    res = examinar(
        conjuntos(emb, feat), y, es_examen,
        np.array([del_campeon[f]["pred_modelo"] for f in fechas_examen]),
        np.array([del_campeon[f]["pred_gemini"] for f in fechas_examen]),
        minimo=args.minimo,
    )
    anotar(res, version)

    if res["n"]:
        print(f"\n{'':14}  F1     acierta")
        for quien in ("campeon", "challenger", "gemini", "frecuente"):
            print(f"  {quien:12}  {res['f1_' + quien]:.3f}  {res['acc_' + quien]:.0%}")
        print(f"  (challenger con features '{res['conjunto']}'; "
              "frecuente = siempre la nota más común, sin leer el poema)")
        for quien in ("campeon", "challenger"):
            if res["f1_" + quien] <= res["f1_frecuente"]:
                print(f"  ⚠ el {quien} no supera a la frecuente")

    if res["decision"] == "faltan_datos":
        print(f"\nTodavía no decido: hacen falta {args.minimo} poemas y hay {res['n']}. "
              "El campeón sigue.")
        return

    if res["decision"] == "conservar":
        print("\nEl challenger no supera al campeón. Se queda el campeón.")
        return

    X = conjuntos(emb, feat)[res["conjunto"]]
    art = crear_artefacto(X, y, res["conjunto"], res["f1_challenger"], corpus)
    MODELOS.mkdir(exist_ok=True)
    ruta = MODELOS / f"{art['version']}.joblib"
    joblib.dump(art, ruta)
    print(f"\nGana el challenger → {ruta.relative_to(RAIZ)}")
    print("Para publicarlo:")
    print(f"  gcloud storage cp {ruta.relative_to(RAIZ)} {BUCKET}/{ruta.name}")
    print(f"  gcloud run services update mestrofa --region us-central1 "
          f"--update-env-vars MESTROFA_MODELO={BUCKET}/{ruta.name}")


if __name__ == "__main__":
    main()
