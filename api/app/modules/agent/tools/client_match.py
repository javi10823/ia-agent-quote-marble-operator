"""Fuzzy matching helpers for client names.

Real operator data has a lot of variance:
  "Estudio MUNGE" vs "Munge" vs "Arq. Munge"  → same client
  "Juan Carlos Perez" vs "Arq. Perez"          → likely same client
  "Estudio Perez" vs "Juan Perez"              → AMBIGUOUS — accept as same,
                                                  but UI shows a warning

Strategy:
  1. Normalize: lowercase, strip accents, collapse whitespace.
  2. Tokenize on whitespace.
  3. Drop stopwords (professional/legal prefixes and short connectors).
  4. Drop tokens shorter than 3 chars.
  5. Return the set of core tokens.

Two names are "fuzzy-same" when their core-token sets share at least one
token of length >= 4 (the 4-char floor prevents collisions on tiny tokens
like "bsa" or "del").
"""
from __future__ import annotations

import re
import unicodedata

# Professional titles, legal forms, common short connectors.
# Kept conservative — when in doubt, leave the token in.
_STOPWORDS: frozenset[str] = frozenset(
    {
        # Professional titles
        "arq", "arquitecto", "arquitecta",
        "dr", "dra", "doctor", "doctora",
        "sr", "sra", "srta", "senor", "senora",
        "ing", "ingeniero", "ingeniera",
        "lic", "licenciado", "licenciada",
        "cont", "cdor", "contador", "contadora",
        # Studio / company words
        "estudio", "consultora", "consultoria",
        "empresa", "compania",
        "grupo", "inmobiliaria",
        # Legal forms
        "sa", "srl", "sl", "sas", "sac", "sacifia",
        "cia", "ltd", "ltda",
        # Connectors
        "y", "e", "o", "u", "de", "del", "la", "el", "los", "las",
        "al", "en", "a",
        # Currency / project noise we sometimes see
        "para", "por",
    }
)

MIN_TOKEN_LEN = 3
MIN_MATCH_LEN = 4


def _strip_accents(text: str) -> str:
    """Remove accents/diacritics and the Spanish 'ñ' (→ 'n')."""
    # NFKD decomposition separates base letters from diacritics.
    decomposed = unicodedata.normalize("NFKD", text)
    # Drop combining marks + convert 'ñ' to 'n' (already handled by NFKD).
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_client_name(raw: str | None) -> str:
    """Lowercase + strip accents + collapse whitespace + trim."""
    if not raw:
        return ""
    s = _strip_accents(str(raw))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def client_core_tokens(raw: str | None) -> frozenset[str]:
    """Return the meaningful tokens of a client name (no stopwords, len>=3).

    Punctuation and digits are stripped. Empty input yields an empty set.
    """
    norm = normalize_client_name(raw)
    if not norm:
        return frozenset()
    # Split on anything that's not a letter (drops dots, commas, digits, etc.)
    tokens = [t for t in re.split(r"[^a-z]+", norm) if t]
    core = {t for t in tokens if len(t) >= MIN_TOKEN_LEN and t not in _STOPWORDS}
    return frozenset(core)


def are_fuzzy_same_client(a: str | None, b: str | None) -> bool:
    """True iff two raw names likely refer to the same client.

    Decision rule:
      1. If both normalize to equal strings → same (fast path).
      2. **Prefix/substring fallback**: one normalized name contiene a la
         otra como substring alineado a palabras. Cubre:
           - "DINALE" ⊂ "DINALE S.A."
           - "Estudio 72" ⊂ "Estudio 72 — Fideicomiso Ventus"
           - "Fideicomiso Ventus" ⊂ "Estudio 72 — Fideicomiso Ventus"
         (Caso Estudio 72 15/04/2026: los tokens core de "Estudio 72" son
         vacíos — "estudio" es stopword y "72" tiene len<3 — por eso
         rows de "Estudio 72" no clusterizaban con "Estudio 72 —
         Fideicomiso Ventus". El substring lo resuelve sin relajar
         stopwords/longitud.)
      3. Else, sus core-token sets deben compartir al menos un token len>=4.

    This is intentionally a bit permissive. A false positive the operator
    can always dismiss; a false negative (blocking a valid group) is more
    annoying, so we err on the lenient side.
    """
    if a is None and b is None:
        return True
    na = normalize_client_name(a)
    nb = normalize_client_name(b)
    if na and na == nb:
        return True
    # Prefix/substring fallback (word-boundary-aware).
    if na and nb:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        # Require >=3 chars to avoid matching noise like "sa" ⊂ "casa xyz".
        if len(shorter) >= 3:
            # Build word-bounded pattern: shorter must appear between word
            # boundaries inside longer. Using re.search with \b anchors.
            import re as _re_sub
            pat = r"(?:^|\s|[-–—_/])" + _re_sub.escape(shorter) + r"(?:$|\s|[-–—_/])"
            if _re_sub.search(pat, longer):
                return True
    ca = client_core_tokens(a)
    cb = client_core_tokens(b)
    shared = ca & cb
    if not shared:
        return False
    return any(len(tok) >= MIN_MATCH_LEN for tok in shared)


def group_quotes_by_client(
    quotes: list, *, name_attr: str = "client_name"
) -> list[list]:
    """Cluster a flat list of quotes into fuzzy same-client groups.

    Greedy single-pass: each quote joins an existing group when fuzzy-matches
    its first member; otherwise starts a new group. O(N·G) which is fine for
    dashboard-sized lists.
    """
    groups: list[list] = []
    for q in quotes:
        name = getattr(q, name_attr, None)
        placed = False
        for g in groups:
            anchor_name = getattr(g[0], name_attr, None)
            if are_fuzzy_same_client(name, anchor_name):
                g.append(q)
                placed = True
                break
        if not placed:
            groups.append([q])
    return groups
