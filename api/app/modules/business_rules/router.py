"""Endpoint público `GET /api/v1/business-rules` v0.

- Sin auth. Pensado para ser fetcheado por el bot web al construir su
  system prompt sin necesidad de credenciales.
- `Cache-Control: max-age=3600` (1h). Bump manual de `version` cuando
  hay cambio breaking — el cliente puede comparar `version` en su
  payload cacheado.
- `ETag` por hash determinístico del payload. Si el contenido no
  cambió, el cliente revalida con `If-None-Match` y el server
  responde 304.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Header, Response

from app.modules.business_rules.rules import build_rules
from app.modules.business_rules.schema import BusinessRulesV0


router = APIRouter(tags=["business-rules"])


def _compute_etag(payload: dict) -> str:
    """Hash determinístico del payload — sirve como ETag stable. Sort
    keys para que el orden de inserción no afecte el hash."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return f'"{digest}"'  # ETag spec exige comillas dobles.


@router.get(
    "/v1/business-rules",
    response_model=BusinessRulesV0,
    summary="Reglas de negocio v0 para el bot web",
)
async def get_business_rules(
    response: Response,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> BusinessRulesV0:
    """Retorna el subset mínimo de reglas que el bot web necesita para
    capturar leads sin romper.

    Headers de respuesta:
        - `Cache-Control: max-age=3600`
        - `ETag: "<hash>"` — el cliente puede usarlo en `If-None-Match`
          para revalidar.

    Status 304 si el ETag entrante coincide con el actual.
    """
    rules = build_rules()
    payload = rules.model_dump()
    etag = _compute_etag(payload)

    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["ETag"] = etag

    # Si el cliente revalida con un ETag idéntico, devolvemos 304 sin
    # body. FastAPI no expone una API limpia para "204/304 con headers"
    # desde un endpoint con `response_model`, así que se setea el
    # status_code en la response y dejamos a Pydantic devolver el
    # modelo (FastAPI lo serializa, pero con status 304 el body es
    # ignorado por la spec HTTP).
    if if_none_match and if_none_match == etag:
        response.status_code = 304

    return rules
