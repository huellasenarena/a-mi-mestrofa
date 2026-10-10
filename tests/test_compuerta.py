"""Pruebas de la compuerta campeón–challenger, con datos sintéticos.

    .venv/bin/python -m pytest tests/
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import compuerta  # noqa: E402
import train  # noqa: E402


def datos(n=90, examen=24, semilla=0):
    """Notas 1/2/3 fáciles de separar en 'emb'; 'feat' es puro ruido."""
    rng = np.random.default_rng(semilla)
    y = np.tile([1, 2, 3], n // 3)
    emb = np.eye(3)[y - 1] * 3 + rng.normal(0, 0.5, (n, 3))
    feat = rng.normal(0, 1, (n, 2))
    es_examen = np.zeros(n, dtype=bool)
    es_examen[-examen:] = True
    return {"emb": emb, "feat": feat}, y, es_examen


def test_con_pocos_poemas_enseña_los_numeros_pero_no_decide():
    cand, y, ex = datos(examen=19)
    malo = np.full(ex.sum(), 1)
    r = compuerta.examinar(cand, y, ex, malo, malo, minimo=20)
    assert r["n"] == 19 and r["decision"] == "faltan_datos"
    assert r["f1_challenger"] > r["f1_campeon"]     # aunque gane, no cambia


def test_sin_examen_no_hay_numeros():
    cand, y, ex = datos()
    ex = np.zeros_like(ex)
    assert compuerta.examinar(cand, y, ex, y[ex], y[ex]) == {"n": 0, "decision": "faltan_datos"}


def test_la_frecuente_responde_la_nota_mas_comun_sin_leer():
    cand, y, ex = datos()
    y = y.copy()
    y[:60] = 1                                      # el corpus es casi todo "1"
    r = compuerta.examinar(cand, y, ex, y[ex], y[ex])
    assert r["acc_frecuente"] == np.mean(y[ex] == 1)


def test_challenger_bueno_contra_campeon_malo_cambia():
    cand, y, ex = datos()
    malo = np.full(ex.sum(), 1)
    r = compuerta.examinar(cand, y, ex, malo, malo)
    assert r["conjunto"] == "emb"          # elige la señal, no el ruido
    assert r["f1_challenger"] > r["f1_campeon"]
    assert r["decision"] == "cambiar"


def test_empate_conserva_al_campeon():
    cand, y, ex = datos()
    perfecto = y[ex]
    r = compuerta.examinar(cand, y, ex, perfecto, perfecto)
    assert r["f1_challenger"] <= r["f1_campeon"]
    assert r["decision"] == "conservar"


def test_el_challenger_nunca_ve_el_poema_que_predice(monkeypatch):
    """Cada entrenamiento del examen deja fuera justo el poema que se predice,
    y la elección de features no toca ningún poema del examen."""
    cand, y, ex = datos()
    firma = {tuple(np.round(fila, 6)) for fila in cand["emb"][ex]}
    vistos = []

    real = train.modelo_logistico

    class Espia:
        def __init__(self):
            self.m = real()

        def fit(self, X, yy):
            vistos.append({tuple(np.round(f, 6)) for f in X})
            self.m.fit(X, yy)
            return self

        def predict(self, X):
            fila = tuple(np.round(X[0], 6))
            assert fila not in vistos[-1], "predijo un poema con el que se entrenó"
            return self.m.predict(X)

        def get_params(self, deep=True):
            return {}

        def set_params(self, **k):
            return self

    monkeypatch.setattr(train, "modelo_logistico", Espia)
    # cross_val_predict clona el estimador: con el espía se salta, así que se
    # comprueba aparte que la selección sólo recibe filas de fuera del examen.
    llamadas = []
    monkeypatch.setattr(compuerta, "cross_val_predict",
                        lambda est, X, yy, cv: (llamadas.append({tuple(np.round(f, 6)) for f in X}),
                                                np.array(yy))[1])
    compuerta.examinar(cand, y, ex, y[ex], y[ex])

    assert len(llamadas) == 2 and all(not (s & firma) for s in llamadas)
    assert len(vistos) == ex.sum()
