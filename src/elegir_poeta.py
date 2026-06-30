#!/usr/bin/env python3
"""Elige al azar un poeta (con su sitio) o un sitio para explorar.

poetas.txt se organiza por secciones:

    [Nombre del sitio | URL]
    Poeta uno
    Poeta dos
    ...

Un sitio SIN poetas debajo es un "sitio-enlace": el programa solo te da
el enlace para que busques tú.

Reparto: por defecto cada SITIO tiene la misma probabilidad; dentro del
sitio elegido, cada poeta es equiprobable. Así un sitio con 676 poetas
no aplasta a uno con 116 ni a los sitios-enlace.

Uso:
    python elegir_poeta.py                    # uno al azar
    python elegir_poeta.py -n 5               # cinco
    python elegir_poeta.py --sitio "Cervantes"
    python elegir_poeta.py --sin-repetir      # no repite entre ejecuciones
    python elegir_poeta.py --por-poeta        # todos los poetas equiprobables
                                              # (ignora los sitios-enlace)
"""
import argparse
import random
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARCHIVO = AQUI / "poetas.txt"
VISTOS = AQUI / ".poetas_vistos.txt"
CABECERA = re.compile(r"^\[(.+?)\s*\|\s*(.+?)\]\s*$")


def cargar_sitios(ruta):
    if not ruta.exists():
        sys.exit(f"No encuentro {ruta.name}.")
    sitios, actual = [], None
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        s = linea.strip()
        if not s or s.startswith("#"):
            continue
        m = CABECERA.match(s)
        if m:
            actual = {"nombre": m.group(1).strip(), "url": m.group(2).strip(), "poetas": []}
            sitios.append(actual)
        elif actual is not None:
            actual["poetas"].append(s)
    if not sitios:
        sys.exit("No hay sitios en la lista.")
    return sitios


def clave(e):
    return f"{e['poeta'] or '(explorar)'} @ {e['sitio']}"


def cargar_vistos():
    if not VISTOS.exists():
        return set()
    return {l.strip() for l in VISTOS.read_text(encoding="utf-8").splitlines() if l.strip()}


def guardar_vistos(v):
    VISTOS.write_text("\n".join(sorted(v)), encoding="utf-8")


def elegir_uno(sitios):
    sitio = random.choice(sitios)  # cada sitio, misma probabilidad
    poeta = random.choice(sitio["poetas"]) if sitio["poetas"] else None
    return {"poeta": poeta, "sitio": sitio["nombre"], "url": sitio["url"]}


def elegir(sitios, n, evitar):
    resultados, claves = [], set(evitar)
    for _ in range(n * 80):
        if len(resultados) >= n:
            break
        e = elegir_uno(sitios)
        if clave(e) not in claves:
            resultados.append(e)
            claves.add(clave(e))
    while len(resultados) < n:  # pocas opciones nuevas: permite repetir
        resultados.append(elegir_uno(sitios))
    return resultados


def elegir_por_poeta(sitios, n):
    todos = [{"poeta": p, "sitio": s["nombre"], "url": s["url"]}
             for s in sitios for p in s["poetas"]]
    if not todos:
        sys.exit("No hay poetas con nombre en los sitios elegidos.")
    return random.sample(todos, min(n, len(todos)))


def main():
    ap = argparse.ArgumentParser(description="Elige poeta/sitio al azar de poetas.txt")
    ap.add_argument("-n", type=int, default=1, help="cuántos elegir (por defecto 1)")
    ap.add_argument("--sitio", default=None,
                    help="solo de los sitios cuyo nombre contenga este texto")
    ap.add_argument("--sin-repetir", action="store_true",
                    help="no repite entre ejecuciones hasta agotar")
    ap.add_argument("--por-poeta", action="store_true",
                    help="todos los poetas equiprobables (ignora los sitios-enlace)")
    args = ap.parse_args()

    sitios = cargar_sitios(ARCHIVO)
    if args.sitio:
        f = args.sitio.lower()
        sitios = [s for s in sitios if f in s["nombre"].lower()]
        if not sitios:
            sys.exit(f"Ningún sitio coincide con «{args.sitio}».")

    n = max(1, args.n)
    if args.por_poeta:
        eleccion = elegir_por_poeta(sitios, n)
    elif args.sin_repetir:
        universo = sum(len(s["poetas"]) for s in sitios) + sum(1 for s in sitios if not s["poetas"])
        vistos = cargar_vistos()
        if len(vistos) >= universo:
            print("(Lista agotada — reinicio el historial.)\n")
            vistos = set()
        eleccion = elegir(sitios, n, vistos)
        guardar_vistos(vistos | {clave(e) for e in eleccion})
    else:
        eleccion = elegir(sitios, n, set())

    total = sum(len(s["poetas"]) for s in sitios)
    expl = sum(1 for s in sitios if not s["poetas"])
    print(f"De {total} poetas en {len(sitios)} sitios ({expl} para explorar), te toca:\n")
    for e in eleccion:
        if e["poeta"]:
            print(f"  → {e['poeta']}")
            print(f"     {e['sitio']} · {e['url']}\n")
        else:
            print(f"  → Explora «{e['sitio']}» y elige tú")
            print(f"     {e['url']}\n")


if __name__ == "__main__":
    main()
