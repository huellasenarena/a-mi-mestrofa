"""Pruebas del servidor, sin red ni Google: blog, almacén y Vertex son falsos.

    .venv/bin/python -m pytest tests/
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.linear_model import LogisticRegression

from servidor.almacen import AlmacenMemoria
from servidor.app import crear_app
from servidor.modelo import Predictor, huella

RAIZ = Path(__file__).resolve().parent.parent
DEMO = json.loads((RAIZ / "data" / "mestrofa-demo.json").read_text())
DEMO_PRED = json.loads((RAIZ / "data" / "mestrofa-demo-predecir.json").read_text())

POEMA_VISTO = "este poema ya estaba en el corpus de entrenamiento y lo conoce"
LARGO = " ".join(["palabra"] * 30)


def entrada(fecha, gusto=None, pdf=False):
    a = {"poet": "Violeta Villalba", "poem_title": "Yo", "book_title": "Fragmentaria"}
    if gusto is not None:
        a["gusto"] = gusto
    if pdf:
        a["pdf"] = "/data/pdfs/x.pdf"
    return {"date": fecha, "analysis": a}


def artefacto_falso():
    """Un campeón de juguete: 'emb' de 4 dims, clases 1/2/3."""
    X = np.eye(3, 4, dtype=np.float32).repeat(5, axis=0)
    y = np.repeat([1, 2, 3], 5)
    return {
        "version": "test-v1", "modelo": LogisticRegression().fit(X, y),
        "conjunto": "emb", "feat_cols": [],
        "claves_qmp": ["qmp:2026-09-01"], "huellas": [huella(POEMA_VISTO)],
    }


class Mundo:
    """El blog, el almacén y Vertex, todos de mentira y controlables."""

    def __init__(self):
        self.entradas = []
        self.textos = {}
        self.almacen = AlmacenMemoria()
        self.gemini = 3
        self.llamadas_gemini = 0
        self.blog_caido = False
        self.predictor = Predictor(artefacto_falso(), self._embeber, self._opinar, "gemini-falso")

    def _embeber(self, texto):
        return [0, 1, 0, 0]            # siempre cae en la nota 2

    def _opinar(self, texto):
        self.llamadas_gemini += 1
        return self.gemini

    def _archivo(self):
        if self.blog_caido:
            raise OSError("sin red")
        return self.entradas

    def cliente(self, tope=50):
        app = crear_app(self.almacen, self.predictor, self._archivo,
                        lambda f: self.textos.get(f, ""),
                        ahora=lambda: datetime(2026, 9, 14, 6, 30, tzinfo=timezone.utc),
                        tope=tope)
        return TestClient(app)


@pytest.fixture
def mundo():
    return Mundo()


# --- /hoy -----------------------------------------------------------------

def test_dia_normal_tiene_la_forma_de_la_demo(mundo):
    mundo.entradas = [entrada("2026-09-13", gusto=2)]
    mundo.textos["2026-09-13"] = LARGO
    c = mundo.cliente()
    assert c.post("/tareas/dia").json()["predichos"] == [{"fecha": "2026-09-13"}]

    hoy = c.get("/hoy").json()
    campos_demo = set(DEMO) - {"_comentario"}
    assert campos_demo <= set(hoy)
    assert set(hoy["marcador"]) == set(DEMO["marcador"])
    assert hoy == {**hoy, "fecha": "2026-09-13", "hay_duelo": True, "gusto": 2,
                   "pred_modelo": 2, "pred_gemini": 3, "fecha_duelo": "2026-09-13",
                   "predicho_el": "2026-09-14T06:30:00Z",
                   "texto_url": "/data/textos/2026/09/2026-09-13.txt"}
    assert hoy["marcador"] == {"desde": "2026-09-13", "total": 1,
                               "modelo": {"aciertos": 1}, "gemini": {"aciertos": 0}}


def test_dia_pdf_enseña_el_ultimo_dia_con_numeros(mundo):
    mundo.entradas = [entrada("2026-09-12", gusto=3), entrada("2026-09-13", gusto=1),
                      entrada("2026-09-14", pdf=True)]
    mundo.textos.update({"2026-09-12": LARGO, "2026-09-13": LARGO + " otro"})
    c = mundo.cliente()
    c.post("/tareas/dia")

    hoy = c.get("/hoy").json()
    assert hoy["fecha"] == "2026-09-14"             # la ficha es la de hoy
    assert hoy["hay_duelo"] is True
    assert hoy["fecha_duelo"] == "2026-09-13"       # los números, del último con texto
    assert hoy["gusto"] == 1
    assert hoy["marcador"]["total"] == 2


def test_dia_pdf_sin_ningun_dia_anterior_no_inventa(mundo):
    mundo.entradas = [entrada("2026-09-10"), entrada("2026-09-14", pdf=True)]
    hoy = mundo.cliente().get("/hoy").json()
    assert hoy["hay_duelo"] is False
    assert all(hoy[k] is None for k in ("gusto", "pred_modelo", "pred_gemini",
                                        "predicho_el", "fecha_duelo"))
    assert hoy["marcador"]["total"] is None         # nada de "0 de 0"
    assert hoy["motivo"] == "sin_texto"


def test_dia_con_texto_sin_prediccion_no_tapa_con_otro_dia(mundo):
    mundo.entradas = [entrada("2026-09-13", gusto=2), entrada("2026-09-14", gusto=3)]
    mundo.textos.update({"2026-09-13": LARGO, "2026-09-14": LARGO + " hoy"})
    c = mundo.cliente()
    c.post("/tareas/dia")
    mundo.almacen._pred.pop("2026-09-14")           # como si hoy hubiera fallado
    c = mundo.cliente()

    hoy = c.get("/hoy").json()
    assert hoy["hay_duelo"] is False
    assert hoy["fecha_duelo"] is None
    assert hoy["motivo"] == "pendiente"
    assert hoy["marcador"]["total"] == 1            # el acumulado sí se enseña


def test_hoy_con_poema_que_el_modelo_ya_vio_dice_ya_visto(mundo):
    mundo.entradas = [entrada("2026-09-13", gusto=2), entrada("2026-09-14", gusto=3)]
    mundo.textos.update({"2026-09-13": LARGO, "2026-09-14": POEMA_VISTO})
    c = mundo.cliente()
    c.post("/tareas/dia")
    hoy = c.get("/hoy").json()
    assert hoy["hay_duelo"] is False and hoy["motivo"] == "ya_visto"


def test_sin_dia_nuevo_la_tarea_no_llama_a_vertex(mundo):
    mundo.entradas = [entrada("2026-09-13", gusto=2)]
    mundo.textos["2026-09-13"] = LARGO
    llamadas = []
    mundo.predictor._embeber = lambda t: (llamadas.append(t), [0, 1, 0, 0])[1]
    c = mundo.cliente()
    c.post("/tareas/dia")
    for _ in range(5):
        c.post("/tareas/dia")
    assert len(llamadas) == 1 and mundo.llamadas_gemini == 1


def test_blog_caido_da_503(mundo):
    mundo.blog_caido = True
    assert mundo.cliente().get("/hoy").status_code == 503


# --- la tarea diaria: el orden que hace honesto el marcador ----------------

def test_cada_dia_se_predice_una_sola_vez(mundo):
    mundo.entradas = [entrada("2026-09-13", gusto=2)]
    mundo.textos["2026-09-13"] = LARGO
    c = mundo.cliente()
    c.post("/tareas/dia")
    mundo.gemini = 1                                  # Gemini cambiaría de opinión…
    assert c.post("/tareas/dia").json()["predichos"] == []
    assert mundo.llamadas_gemini == 1                 # …pero no se le vuelve a preguntar
    assert c.get("/hoy").json()["pred_gemini"] == 3


def test_no_predice_lo_que_el_modelo_ya_vio(mundo):
    mundo.entradas = [entrada("2026-09-01", gusto=3),   # su clave qmp está en el modelo
                      entrada("2026-09-02", gusto=3)]   # su texto está en el corpus
    mundo.textos.update({"2026-09-01": LARGO, "2026-09-02": POEMA_VISTO.upper() + "!"})
    r = mundo.cliente().post("/tareas/dia").json()
    assert r["predichos"] == []
    assert {s["motivo"] for s in r["saltados"]} == {"el modelo ya lo vio al entrenar"}
    assert mundo.almacen.predicciones() == {}


def test_si_gemini_no_responde_no_se_guarda_nada(mundo):
    mundo.entradas = [entrada("2026-09-13", gusto=2)]
    mundo.textos["2026-09-13"] = LARGO
    mundo.gemini = None
    c = mundo.cliente()
    c.post("/tareas/dia")
    assert mundo.almacen.predicciones() == {}
    mundo.gemini = 2
    assert c.post("/tareas/dia").json()["predichos"] == [{"fecha": "2026-09-13"}]


def test_sin_nota_o_sin_texto_no_se_gasta_en_gemini(mundo):
    mundo.entradas = [entrada("2026-09-10"), entrada("2026-09-14", gusto=2, pdf=True)]
    mundo.cliente().post("/tareas/dia")
    assert mundo.llamadas_gemini == 0


# --- /predecir ------------------------------------------------------------

def test_predecir_tiene_la_forma_de_la_demo(mundo):
    r = mundo.cliente().post("/predecir", json={"texto": LARGO})
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == set(DEMO_PRED) - {"_comentario"}
    assert cuerpo["modelo"] == 2 and cuerpo["gemini"] == 3
    assert len(cuerpo["probs"]) == 3 and all(isinstance(p, float) for p in cuerpo["probs"])
    assert cuerpo["aviso"] is None
    assert mundo.almacen.predicciones() == {}         # la caja no toca el marcador


def test_predecir_limites(mundo):
    c = mundo.cliente()
    assert c.post("/predecir", json={"texto": "   "}).status_code == 422
    assert c.post("/predecir", json={"texto": "a" * 6001}).status_code == 422
    assert c.post("/predecir", json={"texto": "a" * 6000}).status_code == 200


def test_predecir_avisos_son_claves_por_prioridad(mundo):
    c = mundo.cliente()
    aviso = lambda t: c.post("/predecir", json={"texto": t}).json()["aviso"]
    assert aviso("pocas palabras") == "corto"
    mundo.gemini = None
    assert aviso("pocas palabras") == "sin_gemini"
    assert aviso(POEMA_VISTO) == "conocido"


def test_tope_diario(mundo):
    c = mundo.cliente(tope=2)
    assert c.post("/predecir", json={"texto": LARGO}).status_code == 200
    assert c.post("/predecir", json={"texto": LARGO}).status_code == 200
    assert c.post("/predecir", json={"texto": LARGO}).status_code == 429
    assert mundo.llamadas_gemini == 2


# --- CORS -----------------------------------------------------------------

def test_cors_solo_para_el_blog(mundo):
    mundo.entradas = [entrada("2026-09-10")]
    c = mundo.cliente()
    ok = c.get("/hoy", headers={"Origin": "https://www.quemalpoema.com"})
    assert ok.headers.get("access-control-allow-origin") == "https://www.quemalpoema.com"
    otro = c.get("/hoy", headers={"Origin": "https://otro.example"})
    assert "access-control-allow-origin" not in otro.headers
    pre = c.options("/predecir", headers={"Origin": "https://www.quemalpoema.com",
                                          "Access-Control-Request-Method": "POST",
                                          "Access-Control-Request-Headers": "content-type"})
    assert pre.status_code == 200


# --- el campeón de verdad ---------------------------------------------------

def test_el_campeon_guardado_carga_y_predice():
    ruta = RAIZ / "modelos" / "campeon.joblib"
    if not ruta.exists():
        pytest.skip("sin campeón; corre src/campeon.py")
    import csv
    import joblib
    art = joblib.load(ruta)
    p = Predictor(art, lambda t: np.zeros(256), lambda t: 2)
    nota, probs = p.modelo(LARGO)
    assert nota in (1, 2, 3) and abs(sum(probs) - 1) < 0.02
    un_poema = next(csv.DictReader((RAIZ / "data" / "poemas.csv").open(encoding="utf-8")))
    assert p.ya_visto(un_poema["texto"])
