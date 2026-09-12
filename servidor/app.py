"""El servidor de la página "A mí me strofa" (quemalpoema.com/site/mestrofa.html).

Rutas:
    GET  /hoy            los números del día (sólo lee lo guardado)
    POST /predecir       la caja de texto: predice en el momento, no guarda nada
    GET  /predicciones   todas las predicciones congeladas, para quien quiera verificar
    POST /tareas/dia     el despertador (Cloud Scheduler): predice los días nuevos

/tareas/dia es pública pero inofensiva: sólo predice días del blog que aún no
tienen predicción, una vez cada uno. Llamarla mil veces no gasta más que una.

Arranque en local:
    MESTROFA_MODELO=modelos/campeon.joblib MESTROFA_ALMACEN=memoria \
        uvicorn --factory servidor.app:desde_entorno --reload
"""
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import importar_qmp as qmp  # noqa: E402

from servidor import logica  # noqa: E402
from servidor.modelo import huella  # noqa: E402

LIMITE = 6000          # el mismo que la página
TOPE_DIARIO = 50       # usos de la caja al día, para todos juntos
ORIGENES = ["https://www.quemalpoema.com", "https://quemalpoema.com"]
CACHE_SEG = 300        # archivo.json y predicciones cambian una vez al día


def _ahora():
    return datetime.now(timezone.utc)


class Cache:
    """Guarda un valor unos minutos. Ahorra consultas a BigQuery y bajadas del blog."""

    def __init__(self, fn, segundos):
        self._fn, self._seg = fn, segundos
        self._valor, self._cuando = None, 0.0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            if self._valor is None or time.monotonic() - self._cuando > self._seg:
                self._valor, self._cuando = self._fn(), time.monotonic()
            return self._valor

    def olvidar(self):
        with self._lock:
            self._valor = None


class Texto(BaseModel):
    texto: str


def crear_app(almacen, predictor, leer_archivo, leer_poema, ahora=_ahora, tope=TOPE_DIARIO):
    """Arma la app. Todo lo de fuera entra por parámetro para poder probarla.

    leer_archivo()      -> lista de entradas de archivo.json
    leer_poema(fecha)   -> texto del poema citado ('' si no hay); lanza si falla la red
    """
    app = FastAPI(title="A mí me strofa")
    app.add_middleware(CORSMiddleware, allow_origins=ORIGENES,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    archivo = Cache(leer_archivo, CACHE_SEG)
    predicciones = Cache(almacen.predicciones, CACHE_SEG)
    poemas = {}
    una_tarea_a_la_vez = threading.Lock()

    def poema(fecha):
        if fecha not in poemas:
            poemas[fecha] = leer_poema(fecha)   # si falla, no se guarda y se reintenta
        return poemas[fecha]

    @app.get("/hoy")
    def hoy():
        try:
            return logica.armar_hoy(archivo(), predicciones(), lambda f: bool(poema(f)))
        except Exception as e:
            raise HTTPException(503, f"No pude leer el blog o las predicciones: {e}")

    @app.get("/predicciones")
    def todas():
        return sorted(
            ({k: p[k] for k in ("fecha", "pred_modelo", "pred_gemini", "probs",
                                "predicho_el", "modelo_version", "gemini_modelo")}
             for p in predicciones().values()),
            key=lambda p: p["fecha"])

    @app.post("/tareas/dia")
    def tarea_dia():
        # Dos despertadores a la vez pagarían dos veces a Gemini por el mismo día.
        with una_tarea_a_la_vez:
            return _tarea_dia()

    def _tarea_dia():
        archivo.olvidar()
        predicciones.olvidar()
        hechos, saltados = [], []
        for fecha in logica.dias_por_predecir(archivo(), predicciones()):
            try:
                texto = poema(fecha)
            except Exception as e:
                saltados.append({"fecha": fecha, "motivo": f"no pude bajar el poema: {e}"})
                continue
            if not texto:
                saltados.append({"fecha": fecha, "motivo": "sin poema en texto"})
                continue
            if predictor.ya_visto(texto, fecha):
                # Predecirlo ahora sería predecir sobre datos de entrenamiento.
                saltados.append({"fecha": fecha, "motivo": "el modelo ya lo vio al entrenar"})
                continue
            nota_modelo, probs = predictor.modelo(texto)
            nota_gemini = predictor.gemini(texto)
            if nota_gemini is None:
                saltados.append({"fecha": fecha, "motivo": "Gemini no respondió; se reintenta"})
                continue
            guardado = almacen.guardar({
                "fecha": fecha,
                "pred_modelo": nota_modelo,
                "pred_gemini": nota_gemini,
                "probs": probs,
                "predicho_el": ahora().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "modelo_version": predictor.version,
                "gemini_modelo": predictor.gemini_modelo,
                "huella": huella(texto),
            })
            (hechos if guardado else saltados).append(
                {"fecha": fecha} if guardado else {"fecha": fecha, "motivo": "ya estaba guardada"})
        predicciones.olvidar()
        return {"predichos": hechos, "saltados": saltados}

    @app.post("/predecir")
    def predecir(cuerpo: Texto):
        texto = cuerpo.texto
        if not texto.strip():
            raise HTTPException(422, "El texto está vacío.")
        if len(texto) > LIMITE:
            raise HTTPException(422, f"El texto pasa de {LIMITE} caracteres.")

        dia = ahora().date().isoformat()
        if almacen.usos(dia) >= tope:
            raise HTTPException(429, "Se acabaron las lecturas de hoy. Vuelve mañana.")
        almacen.anotar_uso(dia)

        nota_modelo, probs = predictor.modelo(texto)
        nota_gemini = predictor.gemini(texto)

        # Una sola clave, la más importante; la frase la pone la página.
        if predictor.ya_visto(texto):
            aviso = "conocido"        # ya estaba en el corpus: el modelo lo vio
        elif nota_gemini is None:
            aviso = "sin_gemini"      # Gemini no dio respuesta legible
        elif len(texto.split()) < 20:
            aviso = "corto"           # menos de 20 palabras: vale poco
        else:
            aviso = None

        return {"modelo": nota_modelo, "gemini": nota_gemini, "probs": probs,
                "aviso": aviso}

    return app


def desde_entorno():
    """La app de verdad, configurada con variables de entorno."""
    from servidor.almacen import AlmacenBigQuery, AlmacenMemoria
    from servidor.modelo import predictor_de_verdad

    if os.environ.get("MESTROFA_ALMACEN", "bigquery") == "memoria":
        almacen = AlmacenMemoria()
    else:
        almacen = AlmacenBigQuery(os.environ.get("MESTROFA_PROYECTO", "a-mi-mestrofa"),
                                  os.environ.get("MESTROFA_DATASET", "mestrofa"))
    predictor = predictor_de_verdad(os.environ["MESTROFA_MODELO"])
    base = os.environ.get("MESTROFA_BLOG", qmp.BASE_QMP)

    def leer_archivo():
        import json
        indice = json.loads(qmp.bajar(f"{base}/data/archivo.json"))
        return indice.get("entries", []) if isinstance(indice, dict) else indice

    def leer_poema(fecha):
        import urllib.error
        try:
            return qmp.extraer_poema_citado(qmp.bajar(qmp.url_del_txt(base, fecha)))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            raise

    return crear_app(almacen, predictor, leer_archivo, leer_poema)
