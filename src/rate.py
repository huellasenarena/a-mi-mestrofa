#!/usr/bin/env python3
"""Calificador de poemas — captura mínima de notas para los datos semilla.

Lee los .txt de data/raw/poems/, te muestra cada poema sin calificar y guarda
tu nota (mal / medio / me gusta) en data/ratings.csv.

- Resumable: salta los que ya calificaste; escribe tras cada nota (a prueba de cierres).
- Sin dependencias externas (solo stdlib) — corre con tu Python tal cual.

Uso:
    python src/rate.py
Teclas:  [1] mal   [2] medio   [3] me gusta   [s] saltar   [q] guardar y salir
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POEMS_DIR = ROOT / "data" / "raw" / "poems"
RATINGS = ROOT / "data" / "ratings.csv"

FIELDS = ["poem_id", "rating", "rated_at"]
CHOICES = {"1": "mal", "2": "medio", "3": "me_gusta"}
LABELS = {"mal": "mal", "medio": "medio", "me_gusta": "me gusta"}


def load_rated() -> dict[str, str]:
    if not RATINGS.exists():
        return {}
    with RATINGS.open(encoding="utf-8") as f:
        return {row["poem_id"]: row["rating"] for row in csv.DictReader(f)}


def append_rating(poem_id: str, rating: str) -> None:
    new_file = not RATINGS.exists()
    with RATINGS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(
            {
                "poem_id": poem_id,
                "rating": rating,
                "rated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def counts(rated: dict[str, str]) -> str:
    c = {"mal": 0, "medio": 0, "me_gusta": 0}
    for r in rated.values():
        if r in c:
            c[r] += 1
    return f"mal {c['mal']} · medio {c['medio']} · me gusta {c['me_gusta']}"


def main() -> None:
    poems = sorted(POEMS_DIR.glob("*.txt"))
    if not poems:
        print("No hay poemas en data/raw/poems/.")
        print("Añade algunos con:  python src/add_poem.py")
        return

    rated = load_rated()
    pending = [p for p in poems if p.stem not in rated]

    if not pending:
        print(f"Todos calificados ({len(rated)}).  {counts(rated)}")
        return

    print(f"{len(rated)} calificados, {len(pending)} pendientes. Empezamos…")
    input("Enter para continuar… ")

    for i, poem in enumerate(pending, 1):
        text = poem.read_text(encoding="utf-8").rstrip("\n")
        lines = text.split("\n")
        title, body = lines[0], "\n".join(lines[1:])

        while True:
            clear()
            done = len(rated)
            print(f"  Pendiente {i}/{len(pending)}  ·  total calificados {done}  ·  {counts(rated)}")
            print("  " + "─" * 60)
            print(f"\n  «{title}»\n")
            print(body)
            print("\n  " + "─" * 60)
            choice = input("  [1] mal  [2] medio  [3] me gusta  [s] saltar  [q] salir > ").strip().lower()

            if choice in CHOICES:
                rating = CHOICES[choice]
                append_rating(poem.stem, rating)
                rated[poem.stem] = rating
                break
            if choice == "s":
                break
            if choice == "q":
                print(f"\nGuardado. {counts(rated)}. ¡Hasta luego!")
                return
            # entrada inválida -> repite

    print(f"\n¡Listo! Calificados {len(rated)} en total.  {counts(rated)}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nInterrumpido — lo calificado ya quedó guardado.")
