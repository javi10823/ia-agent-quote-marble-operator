"""Pulido por ml declarados, cantidad de piletas, y valores por defecto que ya no son silenciosos."""
import copy

from app.modules.quote_engine.calculator import calculate_quote

_PIECES = [
    {"description": "Mesada tramo 1", "largo": 2.4, "prof": 0.6},
    {"description": "Mesada tramo 2", "largo": 1.8, "prof": 0.6},
]


def _calc(**over):
    base = {
        "client_name": "Cliente Test", "project": "Cocina", "material": "Silestone Blanco Norte",
        "pieces": copy.deepcopy(_PIECES), "localidad": "rosario", "colocacion": True,
        "plazo": "30 dias",
    }
    base.update(over)
    r = calculate_quote(base)
    assert r["ok"], r
    return r


def _mo(r, needle):
    return [m for m in r["mo_items"] if needle in m["description"].lower()]


# ── pulido ──────────────────────────────────────────────────────────────────

def test_pulido_con_ml_agrega_item_PUL():
    sin = _calc()
    con = _calc(pulido=True, pulido_ml=4.5)
    item = _mo(con, "pulido de cantos x ml")
    assert len(item) == 1 and item[0]["quantity"] == 4.5
    assert item[0]["total"] == round(item[0]["unit_price"] * 4.5)
    assert con["total_ars"] == sin["total_ars"] + item[0]["total"]


def test_pulido_sinterizado_usa_PUL2():
    gran = _mo(_calc(pulido=True, pulido_ml=2), "pulido de cantos x ml")[0]
    dek = _mo(_calc(material="Dekton Kelya", pulido=True, pulido_ml=2), "pulido de cantos x ml")[0]
    assert dek["unit_price"] > gran["unit_price"]   # PUL2 (9111) > PUL (5384)


def test_pulido_sin_ml_no_cobra_y_avisa():
    sin = _calc()
    r = _calc(pulido=True)
    assert not _mo(r, "pulido de cantos x ml")
    assert r["total_ars"] == sin["total_ars"]
    assert any("pulido_ml" in w for w in r.get("warnings", []))


def test_sin_pulido_no_hay_item_ni_aviso():
    r = _calc()
    assert not _mo(r, "pulido de cantos x ml")
    assert not any("pulido" in w.lower() for w in r.get("warnings", []))


# ── cantidad de piletas Johnson ─────────────────────────────────────────────

def test_cantidad_de_piletas_producto_respeta_pileta_qty():
    r1 = _calc(pileta="empotrada_johnson", pileta_sku="QUADRAQ71A", pileta_qty=1)
    r3 = _calc(pileta="empotrada_johnson", pileta_sku="QUADRAQ71A", pileta_qty=3)
    assert r1["sinks"] and r3["sinks"]
    assert r1["sinks"][0]["quantity"] == 1
    assert r3["sinks"][0]["quantity"] == 3
    unit = r1["sinks"][0]["unit_price"]
    assert r3["total_ars"] - r1["total_ars"] >= 2 * unit


# ── defaults silenciosos → avisos ───────────────────────────────────────────

def test_frentin_sin_ml_avisa():
    r = _calc(frentin=True)
    assert any("Frentín sin metros" in w for w in r.get("warnings", []))


def test_frentin_con_ml_no_avisa():
    r = _calc(frentin=True, frentin_ml=3.2)
    assert not any("Frentín sin metros" in w for w in r.get("warnings", []))


def test_regrueso_sin_ml_avisa():
    r = _calc(regrueso=True)
    assert any("Regrueso sin metros" in w for w in r.get("warnings", []))


def test_sinterizado_con_frentin_avisa_del_refuerzo_mdf():
    r = _calc(material="Dekton Kelya", frentin=True, frentin_ml=2)
    assert any("MDF" in w for w in r.get("warnings", []))
    assert not _mo(r, "refuerzo")   # no se cobra solo
    r2 = _calc(frentin=True, frentin_ml=2)     # Silestone: no aplica
    assert not any("MDF" in w for w in r2.get("warnings", []))
