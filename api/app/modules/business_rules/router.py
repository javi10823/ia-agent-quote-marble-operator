"""Endpoint `GET /api/v1/business-rules` v0 (PR #399 rework).

- **Auth**: `X-API-Key` requerido (mismo esquema que `POST /api/v1/quote`).
  Reusa `verify_api_key` del `quote_engine.router` — no duplica
  middleware. Si `QUOTE_API_KEY` no está seteada en el env (dev),
  el check se skipea para backward-compat con desarrollo local.
- **Cache-Control: max-age=3600** (1h). Bump manual de `version` cuando
  hay cambio breaking — el cliente compara con su payload cacheado.
- **ETag** por hash determinístico. `If-None-Match` matcheando → 304
  sin body.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Header, Response

from app.modules.business_rules.rules import build_rules
from app.modules.business_rules.schema import BusinessRulesV0
from app.modules.quote_engine.router import verify_api_key


router = APIRouter(tags=["business-rules"])


def _compute_etag(payload: dict) -> str:
    """Hash determinístico del payload — ETag estable. `sort_keys` para
    que el orden de inserción no afecte el hash."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return f'"{digest}"'  # ETag spec exige comillas dobles.


@router.get(
    "/v1/business-rules",
    response_model=BusinessRulesV0,
    summary="Reglas de negocio v0 para el bot web (X-API-Key requerido)",
    dependencies=[Depends(verify_api_key)],
)
async def get_business_rules(
    response: Response,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> BusinessRulesV0:
    """Retorna el subset de reglas que el bot web necesita para
    capturar leads sin romper.

    Auth: header `X-API-Key: <key>` (mismo esquema que `/api/v1/quote`).

    Headers de respuesta:
        - `Cache-Control: public, max-age=3600`
        - `ETag: "<hash>"` — usable en `If-None-Match` para revalidar.

    Status 304 si el ETag entrante coincide con el actual.
    """
    rules = build_rules()
    payload = rules.model_dump()
    etag = _compute_etag(payload)

    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["ETag"] = etag

    if if_none_match and if_none_match == etag:
        response.status_code = 304

    return rules
