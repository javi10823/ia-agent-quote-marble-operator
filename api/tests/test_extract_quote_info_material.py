"""El material extraído del mensaje es un nombre, no una frase (coma decimal incluida)."""
import pytest

from app.modules.agent.agent import _extract_quote_info

BRIEF = (
    "Cliente TEST-validacion cierre. Cocina en Silestone Blanco Norte 20mm. "
    "Mesada en L: tramo 1 de 2,40 x 0,60 m y tramo 2 de 1,80 x 0,60 m. "
    "Zócalo de 7 cm en todo el perímetro. Una bacha de empotrar."
)


def test_brief_con_coma_decimal_no_arrastra_texto():
    assert _extract_quote_info(BRIEF)["material"] == "Silestone Blanco Norte 20mm"


@pytest.mark.parametrize("msg,esperado", [
    ("Cliente: Perez, material Silestone Blanco Norte, mesada de 2 m", "Silestone Blanco Norte"),
    ("Granito Gris Mara con zócalo", "Granito Gris Mara"),
    ("MATERIAL: Dekton Kelya\nMesada 2.0 x 0.6", "Dekton Kelya"),
    ("cocina en dekton: mesada de 3 metros", "dekton"),
])
def test_casos_comunes_siguen_igual(msg, esperado):
    assert _extract_quote_info(msg)["material"] == esperado
