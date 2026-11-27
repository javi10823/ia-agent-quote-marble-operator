"""El material extraído del brief es un nombre corto, no una frase."""

from app.modules.quote_engine.brief_analyzer import _clean_material


def test_corta_en_fin_de_frase():
    assert (
        _clean_material("Silestone Blanco Norte 20mm. Mesada en L: tramo 1 de 2")
        == "Silestone Blanco Norte 20mm"
    )


def test_corta_en_dos_puntos_y_salto_de_linea():
    assert _clean_material("Granito Gris Mara: mesada de 2 m") == "Granito Gris Mara"
    assert _clean_material("Dekton Kelya\nMesada isla") == "Dekton Kelya"


def test_nombre_limpio_no_cambia():
    assert _clean_material("Puraprima Onix White") == "Puraprima Onix White"
    assert _clean_material("Dekton Kelya 1.2") == "Dekton Kelya 1.2"


def test_vacio_y_no_string():
    assert _clean_material(None) is None
    assert _clean_material("") is None
    assert _clean_material(". ") is None
