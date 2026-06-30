#!/usr/bin/env python3
"""Features deterministas de cada poema — Python puro, sin LLM.

Por qué en código y no en un LLM (ver CLAUDE.md): un LLM contaría mal los
versos y costaría dinero. Estas features capturan la FORMA del poema (lo que
el embedding se pierde); el embedding capturará tema/tono. Ambos alimentan el
clasificador.

Entrada:  data/poemas.csv   (id, titulo, nota, texto)
Salida:   data/features.csv (id, nota, + columnas de features)

Features:
    n_versos            nº de versos (líneas no vacías)
    n_estrofas          nº de estrofas (bloques separados por línea en blanco)
    long_media_verso    palabras por verso, promedio
    diversidad_lexica   type-token ratio: palabras únicas / palabras totales
    densidad_puntuacion signos de puntuación / caracteres totales

Nota de robustez: la conversión RTF→txt colapsó algunos poemas largos en un
solo párrafo, separando los versos con corridas de 2+ espacios en vez de
saltos de línea. Por eso un "salto de verso" es un newline O una corrida de
2+ espacios — así el conteo funciona en poemas bien formateados y en los
colapsados por igual.
"""
import csv
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "data" / "poemas.csv"
SALIDA = RAIZ / "data" / "features.csv"

PUNTUACION = set(".,;:¡!¿?—-–…«»\"'()[]")
# palabra = secuencia de letras/dígitos (unicode), conserva acentos y ñ.
PALABRA = re.compile(r"\w+", re.UNICODE)
# salto de verso: newline, o corrida de 2+ espacios (RTF colapsado).
SALTO_VERSO = re.compile(r"\n|[ \t]{2,}")


def versos(texto):
    """Lista de versos no vacíos, normalizando el caso RTF colapsado."""
    crudos = SALTO_VERSO.split(texto)
    return [v.strip() for v in crudos if v.strip()]


def estrofas(texto):
    """Nº de estrofas: bloques separados por una línea en blanco (mín. 1).

    Si el poema vino colapsado en un solo párrafo no hay líneas en blanco;
    cuenta como 1 estrofa, que es lo correcto con la info disponible.
    """
    bloques = [b for b in re.split(r"\n\s*\n", texto) if b.strip()]
    return max(1, len(bloques))


def features(texto):
    vs = versos(texto)
    palabras = PALABRA.findall(texto.lower())
    n_palabras = len(palabras)
    n_chars = len(texto)
    return {
        "n_versos": len(vs),
        "n_estrofas": estrofas(texto),
        "long_media_verso": round(n_palabras / len(vs), 3) if vs else 0.0,
        "diversidad_lexica": round(len(set(palabras)) / n_palabras, 3) if n_palabras else 0.0,
        "densidad_puntuacion": round(
            sum(1 for c in texto if c in PUNTUACION) / n_chars, 4
        ) if n_chars else 0.0,
    }


COLUMNAS = [
    "n_versos",
    "n_estrofas",
    "long_media_verso",
    "diversidad_lexica",
    "densidad_puntuacion",
]


def main():
    if not ENTRADA.exists():
        sys.exit(f"No encuentro {ENTRADA}. Corre primero src/parse_seed.py.")

    filas = list(csv.DictReader(ENTRADA.open(encoding="utf-8")))
    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "nota", *COLUMNAS])
        for r in filas:
            feat = features(r["texto"])
            w.writerow([r["id"], r["nota"], *(feat[c] for c in COLUMNAS)])

    print(f"✓ {len(filas)} poemas → {SALIDA.relative_to(RAIZ)}")
    # resumen rápido para ojo humano
    print(f"  columnas: {', '.join(COLUMNAS)}")


if __name__ == "__main__":
    main()
