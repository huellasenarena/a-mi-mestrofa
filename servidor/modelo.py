"""Las dos adivinanzas: el modelo campeón y el Gemini genérico.

El clasificador corre dentro del propio servidor (pesa unos KB), no en un
endpoint de Vertex AI: un endpoint dedicado cobra cada hora que está encendido,
y esto cabe en memoria. Lo que sí va a Vertex es lo que no puede correr aquí:
el embedding (gemini-embedding-001) y la opinión de Gemini. Se pagan por llamada.

Embedding y prompt se importan de src/ tal cual, para que el servidor calcule
exactamente lo mismo que el entrenamiento y el baseline.
"""
import sys
import tempfile
from pathlib import Path

import joblib
import numpy as np

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
from campeon import huella  # noqa: E402
from features import features  # noqa: E402


class Predictor:
    """Envuelve el campeón. `embeber` y `opinar` llegan de fuera (tests: falsos)."""

    def __init__(self, artefacto, embeber, opinar, gemini_modelo=""):
        self.art = artefacto
        self.version = artefacto["version"]
        self.gemini_modelo = gemini_modelo
        self._embeber = embeber
        self._opinar = opinar
        self._claves = set(artefacto["claves_qmp"])
        self._huellas = set(artefacto["huellas"])

    def ya_visto(self, texto, fecha=None):
        """True si el modelo se entrenó con este poema: su predicción no valdría."""
        return (fecha is not None and f"qmp:{fecha}" in self._claves) \
            or huella(texto) in self._huellas

    def _vector(self, texto):
        partes = []
        if "emb" in self.art["conjunto"].split("+"):
            partes.append(np.asarray(self._embeber(texto), dtype=np.float32))
        if "feat" in self.art["conjunto"].split("+"):
            f = features(texto)
            partes.append(np.asarray([f[c] for c in self.art["feat_cols"]], dtype=np.float32))
        return np.hstack(partes).reshape(1, -1)

    def modelo(self, texto):
        """(nota, probs) — probs en el orden de las notas 1, 2, 3."""
        m = self.art["modelo"]
        probs = m.predict_proba(self._vector(texto))[0]
        nota = int(m.classes_[int(np.argmax(probs))])
        return nota, [round(float(p), 2) for p in probs]

    def gemini(self, texto):
        """La nota del Gemini genérico, o None si no dio una respuesta legible.

        Nunca se rellena con un número: ese relleno silencioso fue el bug que
        tuvo roto el baseline de junio a septiembre.
        """
        return self._opinar(texto)


def cargar_artefacto(uri):
    """Lee el campeón de una ruta local o de gs://bucket/ruta."""
    if not uri.startswith("gs://"):
        return joblib.load(uri)
    from google.cloud import storage
    bucket, _, ruta = uri[5:].partition("/")
    with tempfile.NamedTemporaryFile(suffix=".joblib") as tmp:
        storage.Client().bucket(bucket).blob(ruta).download_to_filename(tmp.name)
        return joblib.load(tmp.name)


def predictor_de_verdad(uri):
    """El predictor con Vertex AI de verdad (credenciales ADC, sin claves)."""
    from google import genai
    import embeddings as emb
    import gemini_baseline as gb

    art = cargar_artefacto(uri)
    if art["embedding"]["modelo"] != emb.MODELO or art["embedding"]["dimension"] != emb.DIMENSION:
        raise RuntimeError(f"El campeón se entrenó con otro embedding: {art['embedding']}")

    cliente = genai.Client(vertexai=True, project=emb.PROYECTO, location=emb.REGION)

    def embeber(texto):
        return emb.embeber(cliente, texto)

    def opinar(texto):
        prompt = gb.PROMPT_GENERAL.format(texto=texto[:gb.MAX_CHARS_POEMA])
        nota, ok = gb.predecir(cliente, prompt)
        return nota if ok else None

    return Predictor(art, embeber, opinar, gemini_modelo=gb.MODELO)
