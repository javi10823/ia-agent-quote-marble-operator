"""Medición de precisión del despiece: IA original vs confirmado por el operador."""
from app.modules.quote_engine.despiece_accuracy import compute_accuracy


def _fv(v, status="CONFIRMADO"):
    return {"valor": v, "status": status}


def _dual(*tramos):
    return {"sectores": [{"id": "s1", "tramos": [
        {"id": f"t{i}", "descripcion": f"T{i}", "largo_m": _fv(l), "ancho_m": _fv(a), **extra}
        for i, (l, a, extra) in enumerate(tramos)
    ]}]}


def test_sin_original_no_mide():
    assert compute_accuracy(None, _dual((2, 0.6, {}))) is None
    assert compute_accuracy({}, _dual((2, 0.6, {}))) is None


def test_todo_igual_es_100():
    d = _dual((2.4, 0.6, {}), (1.8, 0.9, {}))
    r = compute_accuracy(d, d)
    assert r["acertadas"] == 2 and r["pct_acierto"] == 100.0
    assert r["corregidas"] == r["inventadas"] == r["faltantes"] == 0


def test_medida_corregida():
    r = compute_accuracy(_dual((2.15, 0.6, {})), _dual((2.05, 0.6, {})))
    assert r["corregidas"] == 1 and r["acertadas"] == 0 and r["pct_acierto"] == 0.0


def test_pieza_inventada_y_faltante():
    ai = _dual((2.4, 0.6, {}), (1.75, 2.35, {}))      # la 2da no existe en el plano
    real = _dual((2.4, 0.6, {}), (0.9, 0.5, {}))      # el operador agregó otra
    r = compute_accuracy(ai, real)
    assert (r["acertadas"], r["inventadas"], r["faltantes"]) == (1, 1, 1)


def test_exacta_gana_a_la_correccion():
    # la IA leyó dos tramos de 2.0 de largo; el operador corrigió uno solo
    ai = _dual((2.0, 0.6, {}), (2.0, 0.7, {}))
    real = _dual((2.0, 0.7, {}), (2.0, 0.5, {}))
    r = compute_accuracy(ai, real)
    assert r["acertadas"] == 1 and r["corregidas"] == 1


def test_derivados_no_cuentan_y_marcas_si():
    ai = _dual((2.4, 0.6, {}), (0.6, 0.6, {"_derived": True}))
    ai["sectores"][0]["tramos"][0]["largo_m"]["status"] = "UNANCHORED"
    r = compute_accuracy(ai, _dual((2.4, 0.6, {})))
    assert r["tramos_ia"] == 1 and r["marcadas_sin_anclar"] == 1
