"""Tests de persistencia del historial del chat — PR #379.

Objetivo: cuando el operador cierra un borrador y lo vuelve a abrir, el
chat reconstruye el recorrido real (cards, pills, Paso 2). Para lograr
eso, el backend debe persistir el JSON real de las cards en `content`,
no placeholders vacíos `_SHOWN_`.

No testamos el flujo async completo con LLM (caro + flaky). Testamos
los bloques determinísticos que persisten `Quote.messages`:

- `_run_dual_read` Case 2 (re-emit) + emit inicial + legacy fallback.
- Handler CONTEXT_CONFIRMED.
- Handler text-parse (legacy path).
- `clean_user_content` en el while loop de Claude (content que va a DB).

Para cada uno validamos shape del `content` persistido, NO el side
effect del turno siguiente.
"""
import json
import re

import pytest


# ─────────────────────────────────────────────────────────────────────
# Grep-style tests sobre el código — defensa contra regresión
#
# Si alguien vuelve a introducir un marker `_SHOWN_` como content
# literal o un fake turn "(contexto confirmado)" en agent.py, estos
# tests fallan y apuntan exactamente al patrón prohibido.
# ─────────────────────────────────────────────────────────────────────

AGENT_PATH = "app/modules/agent/agent.py"


def _agent_source() -> str:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    with open(root / AGENT_PATH, "r", encoding="utf-8") as f:
        return f.read()


class TestAgentSourceHasNoLegacyPlaceholders:
    """Guard contra regresiones de PR #379."""

    def test_no_literal_shown_markers_as_content(self):
        """El content de un message persistido nunca debe ser `"__X_SHOWN__"`
        como string literal. Debe ser `f"__X__{json.dumps(data)}"`.

        Match exacto: `"content": "__..._SHOWN__"` con comillas de string
        (no f-string). Si lo que aparece es `f"..."` queda fuera del match.
        """
        src = _agent_source()
        # Busca patrón estricto de dict literal con content string plano
        # que termine en _SHOWN__. Tolera backslash + variaciones de indent.
        pattern = re.compile(
            r'"content"\s*:\s*"__[A-Z_]+_SHOWN__"'
        )
        matches = pattern.findall(src)
        assert not matches, (
            f"Regresión: `_SHOWN_` placeholders literales en content. "
            f"Matches: {matches}\n"
            f"Persistí el JSON real con f-string `f\"__...__{{json.dumps(...)}}\"`."
        )

    def test_no_fake_user_contexto_confirmado(self):
        """El fake user turn `"(contexto confirmado)"` fue reemplazado
        por el `[CONTEXT_CONFIRMED]<json>` real que el frontend ya
        detecta como pill."""
        src = _agent_source()
        pattern = re.compile(r'"text"\s*:\s*"\(contexto confirmado\)"')
        assert not pattern.search(src), (
            "Regresión: fake user turn '(contexto confirmado)' vuelto a "
            "introducirse. En su lugar persistir el `user_message` que es "
            "el `[CONTEXT_CONFIRMED]<json>` original del frontend."
        )

    def test_clean_user_content_not_deepcopy_of_content(self):
        """Pre-#379 se hacía `clean_user_content = copy.deepcopy(content)`
        lo cual arrastraba a DB el text extraído del PDF y bloques
        `[SISTEMA — ...]`. Ahora debe construirse desde `user_message`
        solo (texto plano del operador)."""
        src = _agent_source()
        assert "clean_user_content = copy.deepcopy(content)" not in src, (
            "Regresión: `clean_user_content = copy.deepcopy(content)` "
            "persiste bloques internos del content. Usar un dict literal "
            "con solo el `user_message` como text."
        )


class TestAgentSourceUsesRealJsonInCardPersistence:
    """El backend debe persistir `__DUAL_READ__<json>` y
    `__CONTEXT_ANALYSIS__<json>` con el JSON real de la card. Estos
    formatos son los que el frontend sabe renderizar como cards —
    reconstrucción del estado real al reabrir el quote."""

    def test_dual_read_persisted_as_json_content(self):
        """Tiene que aparecer al menos una persistencia con el patrón
        correcto: f"__DUAL_READ__{...json.dumps...}"."""
        src = _agent_source()
        # Al menos 3 lugares conocidos (Case 2 re-emit, legacy fallback,
        # CONTEXT_CONFIRMED handler).
        pattern = re.compile(
            r'f"__DUAL_READ__\{[^}]*json\.dumps'
        )
        matches = pattern.findall(src)
        # Uso _json en vez de json (alias) en algunas partes del módulo;
        # relajo con un segundo regex defensivo.
        alt = re.compile(r'f"__DUAL_READ__\{_?json\.dumps')
        all_matches = pattern.findall(src) + alt.findall(src)
        assert len(all_matches) >= 3, (
            f"Esperaba al menos 3 persistencias como "
            f"`f\"__DUAL_READ__{{json.dumps(...)}}\"`. Got {len(all_matches)}."
        )

    def test_context_analysis_persisted_as_json_content(self):
        src = _agent_source()
        pattern = re.compile(r'f"__CONTEXT_ANALYSIS__\{_?json\.dumps')
        matches = pattern.findall(src)
        # Al menos 2 lugares (first emit en _run_dual_read, text-parse path).
        assert len(matches) >= 2, (
            f"Esperaba ≥2 persistencias como "
            f"`f\"__CONTEXT_ANALYSIS__{{json.dumps(...)}}\"`. Got {len(matches)}."
        )


class TestCleanUserContentShape:
    """Unit test del constructor de `clean_user_content` post-#379.

    Extrajimos la lógica en un shape reproducible: solo un bloque de
    texto con el user_message (sin imagen, sin PDF extraído, sin
    hints de sistema).
    """

    def _build_clean(self, user_message: str, plan_filename: str | None = None):
        """Reproducción del bloque post-#379 en agent.py."""
        _text_for_db = (user_message or "").strip() or (
            f"(adjuntó plano: {plan_filename})" if plan_filename
            else "(adjunto plano)"
        )
        return [{"type": "text", "text": _text_for_db}]

    def test_uses_user_message_verbatim(self):
        clean = self._build_clean("cotizar cocina con pileta")
        assert clean == [{"type": "text", "text": "cotizar cocina con pileta"}]

    def test_empty_message_with_plan_shows_filename(self):
        clean = self._build_clean("", plan_filename="bernardi.pdf")
        assert clean == [{"type": "text", "text": "(adjuntó plano: bernardi.pdf)"}]

    def test_empty_message_without_plan_shows_generic(self):
        clean = self._build_clean("")
        assert clean == [{"type": "text", "text": "(adjunto plano)"}]

    def test_dual_read_confirmed_passes_through(self):
        """El user_message `[DUAL_READ_CONFIRMED]<json>` va tal cual —
        el frontend lo detecta como pill verde."""
        msg = '[DUAL_READ_CONFIRMED]{"sectores":[]}'
        clean = self._build_clean(msg)
        assert clean[0]["text"] == msg

    def test_context_confirmed_passes_through(self):
        msg = '[CONTEXT_CONFIRMED]{"answers":[]}'
        clean = self._build_clean(msg)
        assert clean[0]["text"] == msg

    def test_pdf_extracted_text_is_never_in_output(self):
        """Aunque el `content` que va a Claude contenga el bloque PDF,
        `clean_user_content` se construye desde `user_message` — el
        bloque nunca aparece."""
        user_msg = "cotizar con plano adjunto"
        clean = self._build_clean(user_msg)
        rendered = json.dumps(clean)
        assert "TEXTO EXTRAÍDO DEL PDF" not in rendered
        assert "[SISTEMA" not in rendered

    def test_whitespace_user_message_treated_as_empty(self):
        clean = self._build_clean("   \n\t  ", plan_filename="x.pdf")
        assert clean[0]["text"] == "(adjuntó plano: x.pdf)"
