// Fuzzy client-name matching — mirror of api/app/modules/agent/tools/client_match.py.
// Kept intentionally close to the server logic so checkbox gating and
// backend validation agree. If you tweak one, tweak the other.

const STOPWORDS = new Set<string>([
  "arq", "arquitecto", "arquitecta",
  "dr", "dra", "doctor", "doctora",
  "sr", "sra", "srta", "senor", "senora",
  "ing", "ingeniero", "ingeniera",
  "lic", "licenciado", "licenciada",
  "cont", "cdor", "contador", "contadora",
  "estudio", "consultora", "consultoria",
  "empresa", "compania",
  "grupo", "inmobiliaria",
  "sa", "srl", "sl", "sas", "sac", "sacifia",
  "cia", "ltd", "ltda",
  "y", "e", "o", "u", "de", "del", "la", "el", "los", "las",
  "al", "en", "a",
  "para", "por",
]);

const MIN_TOKEN_LEN = 3;
const MIN_MATCH_LEN = 4;

function stripAccents(s: string): string {
  return s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
}

export function normalizeClientName(raw: string | null | undefined): string {
  if (!raw) return "";
  const n = stripAccents(String(raw))
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
  return n;
}

export function clientCoreTokens(
  raw: string | null | undefined
): Set<string> {
  const norm = normalizeClientName(raw);
  if (!norm) return new Set();
  const tokens = norm.split(/[^a-z]+/).filter(Boolean);
  return new Set(
    tokens.filter((t) => t.length >= MIN_TOKEN_LEN && !STOPWORDS.has(t))
  );
}

function _escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function areFuzzySameClient(
  a: string | null | undefined,
  b: string | null | undefined
): boolean {
  if (a == null && b == null) return true;
  const na = normalizeClientName(a);
  const nb = normalizeClientName(b);
  if (na && na === nb) return true;
  // Prefix/substring fallback (word-boundary-aware). Caso Estudio 72:
  // "estudio 72" ⊂ "estudio 72 — fideicomiso ventus". Los core tokens
  // son vacíos (estudio=stopword, 72 len<3), así que sin este fallback
  // el checkbox no permitía agrupar quotes del mismo cliente.
  if (na && nb) {
    const [shorter, longer] = na.length <= nb.length ? [na, nb] : [nb, na];
    if (shorter.length >= 3) {
      const pat = new RegExp(
        `(?:^|\\s|[-–—_/])${_escapeRegex(shorter)}(?:$|\\s|[-–—_/])`,
      );
      if (pat.test(longer)) return true;
    }
  }
  const ca = clientCoreTokens(a);
  const cb = clientCoreTokens(b);
  let found = false;
  ca.forEach((tok) => {
    if (!found && cb.has(tok) && tok.length >= MIN_MATCH_LEN) found = true;
  });
  return found;
}
