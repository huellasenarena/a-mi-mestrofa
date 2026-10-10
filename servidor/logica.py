"""La lógica de la página, sin red ni Google: sólo datos que entran y salen.

Aquí se decide qué dice /hoy y qué días se predicen. Todo lo que habla con
internet (el blog, BigQuery, Vertex) llega de fuera como funciones, así que los
tests lo prueban entero sin gastar un céntimo.

Los textos que ve el lector son del autor y viven en la página (TEXTOS de
site/mestrofa.js). El servidor no manda frases: `motivo` y `aviso` son claves.

La regla que hace honesto el marcador: cada día se predice UNA vez, antes de que
su nota entre al entrenamiento, y esa predicción queda guardada para siempre.
/hoy nunca predice: sólo lee lo guardado.
"""

NOTAS = {1, 2, 3}


def gusto_de(entrada):
    """La nota del poema citado (1/2/3), o None si la entrada no la trae."""
    g = (entrada.get("analysis") or {}).get("gusto")
    try:
        g = int(g)
    except (TypeError, ValueError):
        return None
    return g if g in NOTAS else None


def url_del_txt(fecha):
    return f"/data/textos/{fecha[:4]}/{fecha[5:7]}/{fecha}.txt"


def ficha(entrada):
    a = entrada.get("analysis") or {}
    return {
        "fecha": entrada["date"],
        "poeta": a.get("poet") or "",
        "titulo": a.get("poem_title") or "",
        "libro": a.get("book_title") or "",
        "texto_url": url_del_txt(entrada["date"]),
    }


def marcador(entradas, predicciones):
    """Aciertos acumulados de los días con nota Y predicción guardada.

    La nota se lee del blog en cada consulta (es la fuente de verdad); la
    predicción, de lo guardado. Sin ningún día contado, todo va en null: la
    página entonces no enseña marcador, en vez de un "0 de 0".
    """
    contados = [(e["date"], gusto_de(e), predicciones[e["date"]])
                for e in entradas
                if gusto_de(e) is not None and e["date"] in predicciones]
    if not contados:
        return {"desde": None, "total": None,
                "modelo": {"aciertos": None}, "gemini": {"aciertos": None}}
    return {
        "desde": min(f for f, _, _ in contados),
        "total": len(contados),
        "modelo": {"aciertos": sum(1 for _, g, p in contados if p["pred_modelo"] == g)},
        "gemini": {"aciertos": sum(1 for _, g, p in contados if p["pred_gemini"] == g)},
    }


def _duelo(entrada, predicciones):
    """Los números de un día, o None si falta la nota o la predicción."""
    g = gusto_de(entrada)
    p = predicciones.get(entrada["date"])
    if g is None or p is None:
        return None
    return {
        "hay_duelo": True,
        "gusto": g,
        "pred_modelo": p["pred_modelo"],
        "pred_gemini": p["pred_gemini"],
        "predicho_el": p["predicho_el"],
        "fecha_duelo": entrada["date"],
    }


def _sin_duelo(motivo):
    return {
        "hay_duelo": False,
        "motivo": motivo,
        "gusto": None,
        "pred_modelo": None,
        "pred_gemini": None,
        "predicho_el": None,
        "fecha_duelo": None,
    }


def armar_hoy(entradas, predicciones, tiene_texto, ya_visto=lambda fecha: False, hasta=None):
    """La respuesta de GET /hoy.

    entradas      archivo.json del blog, en cualquier orden
    predicciones  {fecha: fila guardada}
    tiene_texto   fecha -> bool: si ese día trae poema citado en texto
    ya_visto      fecha -> bool: si el modelo se entrenó con el poema de ese día
    hasta         'YYYY-MM-DD': la fecha del lector; lo posterior no existe todavía

    "Hoy" es la última entrada publicada hasta `hasta`, como en la portada del
    blog: el autor programa entradas por adelantado y ésas no se enseñan antes
    de su día, ni cuentan en el marcador.

    `motivo` (sólo si hay_duelo es false):
        sin_entradas  el blog no tiene entradas
        sin_nota      hoy hay poema pero no nota
        pendiente     hoy hay poema y nota; la predicción llega en minutos
        ya_visto      el modelo se entrenó con el poema de hoy: no habrá duelo
        sin_texto     hoy no hay poema en texto y ningún día anterior tiene duelo

    - Hoy con nota y predicción → sus números.
    - Hoy con poema en texto pero sin nota o sin predicción → nada. No se tapa
      un fallo de hoy con los números de otro día.
    - Hoy sin poema en texto (PDF) → los números del último día anterior que
      los tenga, con fecha_duelo para que la página diga de qué día son.
    """
    entradas = sorted((e for e in entradas if hasta is None or e["date"] <= hasta),
                      key=lambda e: e["date"])
    if not entradas:
        return {**_sin_duelo("sin_entradas"),
                "marcador": marcador([], predicciones)}

    hoy = entradas[-1]
    base = {**ficha(hoy), "marcador": marcador(entradas, predicciones)}

    duelo = _duelo(hoy, predicciones)
    if duelo:
        return {**base, **duelo}

    if tiene_texto(hoy["date"]):
        if gusto_de(hoy) is None:
            motivo = "sin_nota"
        elif ya_visto(hoy["date"]):
            motivo = "ya_visto"
        else:
            motivo = "pendiente"      # el despertador pasa cada 10 minutos
        return {**base, **_sin_duelo(motivo)}

    for anterior in reversed(entradas[:-1]):
        duelo = _duelo(anterior, predicciones)
        if duelo:
            return {**base, **duelo}
    return {**base, **_sin_duelo("sin_texto")}


def dias_por_predecir(entradas, predicciones):
    """Fechas con nota y todavía sin predicción, de la más vieja a la más nueva.

    Sólo se predice lo que lleva nota: un día sin nota nunca contaría en el
    marcador y la llamada a Gemini sería gasto tirado.
    """
    return sorted(e["date"] for e in entradas
                  if gusto_de(e) is not None and e["date"] not in predicciones)
