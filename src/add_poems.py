#!/usr/bin/env python3
"""Añade en lote los poemas pegados en data/nuevos.txt al corpus.

Pensado para tu flujo: pegas muchos poemas de una vez en un archivo de texto
plano y corres esto UNA vez. Evita el problema del RTF (los versos pegados
desde el navegador conservan sus saltos de línea) y evita casar por orden con
una lista de notas aparte: aquí cada poema lleva su nota arriba.

Formato de data/nuevos.txt:
    <nota 1/2/3>
    <texto del poema, varias líneas>
    ===
    <nota>
    <texto>
    ===
    ...
Las líneas que empiezan con # se ignoran.

Qué hace:
    1. Lee y valida los bloques de data/nuevos.txt.
    2. Los añade a data/poemas.csv con ids nuevos (continúa la numeración).
    3. Archiva lo procesado en data/nuevos_procesados/<fecha-hora>.txt y deja
       nuevos.txt vacío (con su plantilla), para que no se añada dos veces.

Uso:
    python src/add_poems.py            # añade
    python src/add_poems.py --dry-run  # solo muestra qué añadiría, sin tocar nada
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NUEVOS = RAIZ / "data" / "nuevos.txt"
CORPUS = RAIZ / "data" / "poemas.csv"
ARCHIVO_DIR = RAIZ / "data" / "nuevos_procesados"

PLANTILLA = NUEVOS  # se reescribe con el encabezado tras procesar


def parsear_bloques(texto):
    """Devuelve [(nota, titulo, cuerpo), ...] desde el contenido de nuevos.txt."""
    poemas, errores = [], []
    bloques = texto.split("\n===")
    for n_bloque, bruto in enumerate(bloques, 1):
        # quita comentarios y espacios sobrantes
        lineas = [l for l in bruto.splitlines() if not l.strip().startswith("#")]
        # recorta líneas vacías al inicio/fin del bloque
        while lineas and not lineas[0].strip():
            lineas.pop(0)
        while lineas and not lineas[-1].strip():
            lineas.pop()
        if not lineas:
            continue  # bloque vacío (p. ej. tras el último ===)

        nota_str = lineas[0].strip()
        if nota_str not in ("1", "2", "3"):
            errores.append(
                f"Bloque {n_bloque}: la primera línea debe ser 1, 2 o 3 "
                f"(encontré: «{nota_str[:30]}»)."
            )
            continue
        cuerpo_lineas = lineas[1:]
        # título opcional si la primera línea del cuerpo empieza con 'Título:'
        titulo = ""
        if cuerpo_lineas and cuerpo_lineas[0].strip().lower().startswith("título:"):
            titulo = cuerpo_lineas[0].split(":", 1)[1].strip()
            cuerpo_lineas = cuerpo_lineas[1:]
        cuerpo = "\n".join(cuerpo_lineas).strip()
        if not cuerpo:
            errores.append(f"Bloque {n_bloque}: poema sin texto.")
            continue
        poemas.append((int(nota_str), titulo, cuerpo))
    return poemas, errores


def max_id():
    if not CORPUS.exists():
        return 0
    ids = [int(r["id"]) for r in csv.DictReader(CORPUS.open(encoding="utf-8"))]
    return max(ids) if ids else 0


def main():
    ap = argparse.ArgumentParser(description="Añade poemas en lote desde nuevos.txt")
    ap.add_argument("--dry-run", action="store_true",
                    help="muestra qué añadiría sin escribir nada")
    args = ap.parse_args()

    if not NUEVOS.exists():
        sys.exit(f"No encuentro {NUEVOS}.")
    if not CORPUS.exists():
        sys.exit(f"No encuentro {CORPUS}. Corre primero src/parse_seed.py.")

    contenido = NUEVOS.read_text(encoding="utf-8")
    poemas, errores = parsear_bloques(contenido)

    if errores:
        print("⚠ Encontré problemas; no añado nada hasta que los corrijas:")
        for e in errores:
            print(f"  - {e}")
        sys.exit(1)
    if not poemas:
        sys.exit("No hay poemas nuevos en data/nuevos.txt (¿solo está la plantilla?).")

    inicio = max_id() + 1
    dist = {n: sum(1 for p in poemas if p[0] == n) for n in (1, 2, 3)}
    print(f"Listos para añadir: {len(poemas)} poemas (ids {inicio}–{inicio+len(poemas)-1})")
    print(f"  Distribución de notas: 1={dist[1]}  2={dist[2]}  3={dist[3]}")
    for i, (nota, tit, cuerpo) in enumerate(poemas, inicio):
        vista = (tit or cuerpo.split('\n')[0])[:50]
        print(f"  #{i}  nota {nota}  · {vista}")

    if args.dry_run:
        print("\n(--dry-run: no escribí nada.)")
        return

    # 1. Añade al corpus. Se escriben las columnas que tenga el CSV: desde que
    # src/importar_qmp.py existe puede llevar `fuente` y `fecha_origen`, que
    # aquí van vacías (estos poemas los pegaste a mano, no vienen del blog).
    with CORPUS.open(encoding="utf-8", newline="") as f:
        columnas = next(csv.reader(f), ["id", "titulo", "nota", "texto"])
    with CORPUS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        for i, (nota, tit, cuerpo) in enumerate(poemas, inicio):
            fila = {"id": i, "titulo": tit, "nota": nota, "texto": cuerpo}
            w.writerow({c: fila.get(c, "") for c in columnas})

    # 2. Archiva lo procesado y limpia nuevos.txt.
    ARCHIVO_DIR.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    (ARCHIVO_DIR / f"{sello}.txt").write_text(contenido, encoding="utf-8")
    NUEVOS.write_text(_encabezado(), encoding="utf-8")

    print(f"\n✓ Añadidos {len(poemas)} poemas → {CORPUS.relative_to(RAIZ)} "
          f"(total ahora: {max_id()})")
    print(f"  Copia de seguridad en {ARCHIVO_DIR.relative_to(RAIZ)}/{sello}.txt")
    print("  nuevos.txt quedó limpio para la próxima tanda.")
    print("\nCuando quieras ver cómo cambió el modelo, corre:")
    print("  python src/features.py && python src/embeddings.py --force \\")
    print("    && python src/gemini_baseline.py --force && python src/snapshot.py")


def _encabezado():
    """Plantilla mínima para dejar nuevos.txt listo otra vez."""
    return (
        "# Pega aquí tus poemas nuevos. Primera línea de cada bloque = nota "
        "(1/2/3).\n# Separa poemas con una línea:  ===\n# Guarda como texto "
        "plano (.txt), no RTF.\n"
    )


if __name__ == "__main__":
    main()
