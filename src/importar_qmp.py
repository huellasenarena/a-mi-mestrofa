#!/usr/bin/env python3
"""Importa al corpus los poemas citados en Que Mal Poema que ya llevan nota.

El autor publica un poema al día en quemalpoema.com: uno propio, uno citado de
otro autor y un análisis. Desde el 12 sep 2026 cada entrada lleva además su
nota de gusto del poema **citado**, y el blog la publica como metadato. Este
script la trae aquí.

Cómo funciona:

    1. Baja https://www.quemalpoema.com/data/archivo.json (metadatos de todas
       las entradas; nunca trae texto de poema, es un invariante de aquel repo).
    2. Se queda con las entradas que traen `analysis.gusto` (1, 2 o 3).
    3. Baja el .txt de cada una y le saca la sección `# POEMA_CITADO`.
    4. Descarta lo que ya esté en el corpus, por la clave de origen qmp:FECHA.
    5. Lo añade a data/poemas.csv con `fuente` y `fecha_origen`.

Sólo entra el poema **citado**. El poema propio del autor no sirve como señal:
lo calificaría siempre alto y el modelo aprendería "esto lo escribió él" en vez
de "esto le gusta".

Las entradas en modo PDF (poemas visuales, capítulos de novela) no tienen texto
y se caen solas. Lo que no se filtra por idioma: el corpus es sólo español y un
detector automático sería otra dependencia y se equivocaría con poemas cortos,
así que el script no escribe nada hasta que mires la lista y pases --aplicar.

Acoplamiento en un solo sentido: QMP no sabe que este proyecto existe. Aquí se
consume una API pública; un fallo de este lado no puede romper el blog.

Uso:
    python src/importar_qmp.py             # enseña qué añadiría, no escribe
    python src/importar_qmp.py --aplicar   # lo añade a data/poemas.csv
"""
import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "data" / "poemas.csv"

BASE_QMP = "https://www.quemalpoema.com"

# Columnas del corpus. Las dos últimas las añadió este importador: el corpus
# original (los 187 primeros poemas) las lleva vacías.
COLUMNAS = ["id", "titulo", "nota", "texto", "fuente", "fecha_origen"]

NOTAS_VALIDAS = {"1", "2", "3"}

# Encabezados de sección del .txt de QMP: una línea "# NOMBRE" y nada más.
CABECERA_RE = re.compile(r"^#\s+[A-Z_]+\s*$")


# --------------------------------------------------------------------------
# Leer del blog
# --------------------------------------------------------------------------

# Sin User-Agent propio, urllib manda "Python-urllib/3.x" y el sitio devuelve
# 403. Hace falta uno cualquiera que no sea ese.
AGENTE = "importar_qmp/1.0 (+https://github.com/huellasenarena)"


def bajar(url, timeout=30):
    # quemalpoema.com redirige (301) a www.quemalpoema.com; urllib sigue
    # redirecciones por su cuenta.
    pet = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(pet, timeout=timeout) as r:
        return r.read().decode("utf-8")


def url_del_txt(base, fecha):
    return f"{base}/data/textos/{fecha[:4]}/{fecha[5:7]}/{fecha}.txt"


def limpiar_marcas(poema):
    """Quita las marcas de maquetación del blog: son tipografía, no poema.

    En QMP, '|' fija una sangría (el carácter no se dibuja) y '>>' al principio
    de un verso lo alinea a la derecha. Dejarlas dentro metería ruido en el
    embedding y en las features de forma.
    """
    fuera = []
    for linea in poema.split("\n"):
        linea = re.sub(r"^\s*>>\s*", "", linea)
        linea = linea.replace("|", "")
        fuera.append(linea.rstrip())
    return "\n".join(fuera).strip()


def extraer_poema_citado(txt):
    """Devuelve el contenido de '# POEMA_CITADO', o '' si no hay o está vacío."""
    lineas = txt.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fuera = []
    dentro = False
    for linea in lineas:
        if CABECERA_RE.match(linea.strip()):
            if linea.strip() == "# POEMA_CITADO":
                dentro = True
                continue
            if dentro:
                break          # empezó la sección siguiente
            continue
        if dentro:
            fuera.append(linea)
    return limpiar_marcas("\n".join(fuera))


# --------------------------------------------------------------------------
# El corpus
# --------------------------------------------------------------------------

def leer_corpus(ruta):
    if not ruta.exists():
        sys.exit(f"No encuentro {ruta}. Corre primero src/parse_seed.py.")
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def migrar_columnas(ruta, filas):
    """Añade `fuente` y `fecha_origen` al CSV si todavía no están.

    Se corre sola la primera vez. Las filas existentes se quedan con las dos
    casillas vacías: no sabemos de dónde salieron y no se inventa nada.
    """
    with ruta.open(encoding="utf-8", newline="") as f:
        cabecera = next(csv.reader(f), [])
    if cabecera == COLUMNAS:
        return False
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        for fila in filas:
            w.writerow({c: (fila.get(c) or "") for c in COLUMNAS})
    return True


def siguiente_id(filas):
    ids = [int(f["id"]) for f in filas if str(f.get("id", "")).strip().isdigit()]
    return (max(ids) + 1) if ids else 1


def titulo_de(entrada, poema):
    t = (entrada.get("analysis", {}).get("poem_title") or "").strip()
    if t:
        return t
    for linea in poema.split("\n"):
        if linea.strip():
            return linea.strip()[:80]
    return ""


# --------------------------------------------------------------------------

def recolectar(base, ya_estan, avisar):
    """Devuelve (nuevos, saltados). nuevos = [(clave, fecha, titulo, nota, texto)]."""
    try:
        indice = json.loads(bajar(f"{base}/data/archivo.json"))
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        sys.exit(f"No pude leer archivo.json de {base}: {e}")

    if isinstance(indice, dict):          # por si algún día lleva envoltorio
        indice = indice.get("entries", [])

    nuevos, saltados = [], []
    for entrada in sorted(indice, key=lambda e: e.get("date", "")):
        fecha = entrada.get("date", "")
        clave = f"qmp:{fecha}"
        nota = entrada.get("analysis", {}).get("gusto")

        if nota is None:
            continue                       # entrada anterior a la nota
        if str(nota) not in NOTAS_VALIDAS:
            saltados.append((fecha, f"nota rara: {nota!r}"))
            continue
        if clave in ya_estan:
            continue                       # ya importada

        try:
            txt = bajar(url_del_txt(base, fecha))
        except urllib.error.URLError as e:
            saltados.append((fecha, f"no pude bajar el .txt: {e}"))
            continue

        poema = extraer_poema_citado(txt)
        if not poema:
            saltados.append((fecha, "sin poema en texto (modo PDF)"))
            continue

        nuevos.append((clave, fecha, titulo_de(entrada, poema), str(nota), poema))
        avisar(f"  · {fecha} — nota {nota} — {titulo_de(entrada, poema)[:50]}")

    return nuevos, saltados


def main():
    ap = argparse.ArgumentParser(description="Importa poemas calificados desde Que Mal Poema")
    ap.add_argument("--aplicar", action="store_true",
                    help="escribe en data/poemas.csv (por defecto sólo enseña)")
    ap.add_argument("--base", default=BASE_QMP,
                    help="raíz del sitio (para probar contra una copia local)")
    args = ap.parse_args()

    filas = leer_corpus(CORPUS)
    ya_estan = {(f.get("fuente") or "").strip() for f in filas} - {""}
    print(f"Corpus: {len(filas)} poemas, {len(ya_estan)} venidos del blog.")
    print(f"Leyendo {args.base} …")

    nuevos, saltados = recolectar(args.base, ya_estan, print)

    if saltados:
        print(f"\nSaltados ({len(saltados)}):")
        for fecha, motivo in saltados:
            print(f"  · {fecha} — {motivo}")

    if not nuevos:
        print("\nNada nuevo que importar.")
        return

    dist = {n: sum(1 for x in nuevos if x[3] == n) for n in "123"}
    print(f"\nNuevos: {len(nuevos)}  ·  notas 1={dist['1']} 2={dist['2']} 3={dist['3']}")

    if not args.aplicar:
        print("\n(Sólo he mirado. Pasa --aplicar para añadirlos.)")
        return

    if migrar_columnas(CORPUS, filas):
        print(f"\nAñadí las columnas {COLUMNAS[-2]} y {COLUMNAS[-1]} al corpus.")

    inicio = siguiente_id(filas)
    with CORPUS.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        for i, (clave, fecha, titulo, nota, texto) in enumerate(nuevos, inicio):
            w.writerow({"id": i, "titulo": titulo, "nota": nota, "texto": texto,
                        "fuente": clave, "fecha_origen": fecha})

    print(f"Añadidos {len(nuevos)} poemas (ids {inicio}–{inicio + len(nuevos) - 1}).")
    print("Ahora toca: src/embeddings.py, src/features.py y src/train.py.")


if __name__ == "__main__":
    main()
