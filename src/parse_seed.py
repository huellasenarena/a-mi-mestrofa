#!/usr/bin/env python3
"""Convierte los .rtf semilla (poemas + calificaciones) en un CSV limpio.

Entrada (en la raíz del repo):
    poemas.rtf          — poemas separados por un marcador 'Título:' (a veces
                          con el acento roto: 'Tîtulo:', 'Tîítulo:').
    calificaciones.rtf  — lista numerada 'N. <título>: <nota>' con nota 1/2/3.

Salida:
    data/poemas.csv     — id, titulo, nota, texto

Decisiones:
- Se usa `textutil` (nativo de macOS) para pasar RTF→txt: limpia el formato
  mucho mejor que cualquier regex sobre los códigos de control del RTF.
- Poemas y notas se casan POR ORDEN, no por título. Los títulos en el RTF
  vienen sucios y varios están vacíos; ambos archivos van 1↔1 en el mismo
  orden, así que la posición es la llave fiable.
- Nota: 1 = no me gusta, 2 = medio, 3 = me gusta.
"""
import csv
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
POEMAS_RTF = RAIZ / "poemas.rtf"
CALIF_RTF = RAIZ / "calificaciones.rtf"
SALIDA = RAIZ / "data" / "poemas.csv"

# 'Título:' tolerante a acentos rotos del RTF (Tîtulo, Tîítulo, ...).
MARCADOR = re.compile(r"^t.{0,2}tulo:\s*(.*)$", re.IGNORECASE)
# 'N. <título>: <nota>' — la nota es el último 1/2/3 de la línea.
NOTA = re.compile(r"^\s*(\d+)\.\s*(.*?):\s*([123])\s*$")


def rtf_a_txt(ruta_rtf):
    """Convierte un .rtf a texto plano con textutil y lo devuelve como str."""
    if not ruta_rtf.exists():
        sys.exit(f"No encuentro {ruta_rtf.name} en {ruta_rtf.parent}.")
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        destino = Path(tmp.name)
    subprocess.run(
        ["textutil", "-convert", "txt", str(ruta_rtf), "-output", str(destino)],
        check=True,
    )
    texto = destino.read_text(encoding="utf-8")
    destino.unlink(missing_ok=True)
    return texto


def partir_poemas(texto):
    """Devuelve [(titulo, cuerpo), ...] partiendo por el marcador de título."""
    poemas, titulo, cuerpo = [], None, []
    for linea in texto.splitlines():
        m = MARCADOR.match(linea.strip())
        if m:
            if titulo is not None:
                poemas.append((titulo, "\n".join(cuerpo).strip()))
            titulo, cuerpo = m.group(1).strip(), []
        elif titulo is not None:
            cuerpo.append(linea)
    if titulo is not None:
        poemas.append((titulo, "\n".join(cuerpo).strip()))
    return poemas


def partir_notas(texto):
    """Devuelve [(titulo, nota), ...] de la lista numerada de calificaciones."""
    notas = []
    for linea in texto.splitlines():
        m = NOTA.match(linea)
        if m:
            notas.append((m.group(2).strip(), int(m.group(3))))
    return notas


def main():
    poemas = partir_poemas(rtf_a_txt(POEMAS_RTF))
    notas = partir_notas(rtf_a_txt(CALIF_RTF))

    if len(poemas) != len(notas):
        sys.exit(
            f"Descuadre: {len(poemas)} poemas vs {len(notas)} notas. "
            "Revisa los marcadores antes de casar por orden."
        )

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "titulo", "nota", "texto"])
        for i, ((tit_p, cuerpo), (tit_n, nota)) in enumerate(zip(poemas, notas), 1):
            # El título de las notas suele estar más limpio; si el del poema
            # está vacío, usamos el de la lista de calificaciones.
            titulo = tit_p or tit_n
            w.writerow([i, titulo, nota, cuerpo])

    vacios = sum(1 for _, c in poemas if not c)
    dist = {n: sum(1 for _, x in notas if x == n) for n in (1, 2, 3)}
    print(f"✓ {len(poemas)} poemas → {SALIDA.relative_to(RAIZ)}")
    print(f"  Distribución de notas: 1={dist[1]}  2={dist[2]}  3={dist[3]}")
    if vacios:
        print(f"  ⚠ {vacios} poema(s) con cuerpo vacío — revísalos a mano.")


if __name__ == "__main__":
    main()
