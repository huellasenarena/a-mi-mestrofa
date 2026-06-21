#!/usr/bin/env python3
"""Añade un poema al corpus.

Uso:
    python src/add_poem.py
    -> te pide el título, luego pegas el poema y terminas con Ctrl-D.

Guarda cada poema como un .txt numerado en data/raw/poems/.
La primera línea del archivo es el título; el resto, el cuerpo.
Sin dependencias externas (solo stdlib).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

POEMS_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "poems"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[áàä]", "a", text)
    text = re.sub(r"[éèë]", "e", text)
    text = re.sub(r"[íìï]", "i", text)
    text = re.sub(r"[óòö]", "o", text)
    text = re.sub(r"[úùü]", "u", text)
    text = re.sub(r"ñ", "n", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:40] or "sin-titulo"


def next_index() -> int:
    POEMS_DIR.mkdir(parents=True, exist_ok=True)
    nums = []
    for p in POEMS_DIR.glob("*.txt"):
        m = re.match(r"(\d+)-", p.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def main() -> None:
    title = input("Título del poema: ").strip()
    print("Pega el poema y pulsa Ctrl-D cuando termines:\n")
    body = sys.stdin.read().strip()

    if not body:
        print("\nCuerpo vacío — no guardo nada.")
        return

    idx = next_index()
    fname = f"{idx:03d}-{slugify(title)}.txt"
    path = POEMS_DIR / fname
    # Convención: primera línea = título, resto = cuerpo.
    path.write_text(f"{title}\n{body}\n", encoding="utf-8")
    print(f"\nGuardado: data/raw/poems/{fname}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
