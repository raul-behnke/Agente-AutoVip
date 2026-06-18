"""GHL Opportunities / Pipeline endpoints (Fase 3 — camada comercial).

Permite ligar o atendimento da IA a uma oportunidade do funil de vendas do
GHL, fechando o gap comercial (vendas atribuíveis à IA). Todas as funções são
best-effort: erro de API é propagado pro caller, que engole e loga.
"""
from __future__ import annotations

import httpx
from loguru import logger

from app.config import settings
from app.ghl.client import request

_VERSION = "2021-07-28"


async def search_opportunity(contact_id: str) -> str | None:
    """GET /opportunities/search — retorna o id da 1ª oportunidade do contato."""
    try:
        resp = await request(
            "GET",
            "/opportunities/search",
            version=_VERSION,
            params={
                "location_id": settings.ghl_location_id,
                "contact_id": contact_id,
                "limit": 1,
            },
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404):
            return None
        raise
    data = resp.json()
    opps = data.get("opportunities") or []
    if not opps:
        return None
    return opps[0].get("id")


async def create_opportunity(
    contact_id: str,
    name: str,
    *,
    monetary_value: float | None = None,
    status: str = "open",
) -> dict:
    """POST /opportunities/ — cria oportunidade no pipeline configurado."""
    body: dict = {
        "pipelineId": settings.ghl_pipeline_id,
        "locationId": settings.ghl_location_id,
        "contactId": contact_id,
        "name": name,
        "status": status,
    }
    if settings.ghl_pipeline_stage_id:
        body["pipelineStageId"] = settings.ghl_pipeline_stage_id
    if monetary_value is not None:
        body["monetaryValue"] = monetary_value
    resp = await request("POST", "/opportunities/", version=_VERSION, json=body)
    return resp.json()


async def update_opportunity(
    opportunity_id: str,
    *,
    stage_id: str | None = None,
    status: str | None = None,
    monetary_value: float | None = None,
) -> dict:
    """PUT /opportunities/{id} — atualiza estágio/status/valor."""
    body: dict = {}
    if stage_id:
        body["pipelineStageId"] = stage_id
    if status:
        body["status"] = status
    if monetary_value is not None:
        body["monetaryValue"] = monetary_value
    resp = await request(
        "PUT", f"/opportunities/{opportunity_id}", version=_VERSION, json=body
    )
    try:
        return resp.json()
    except ValueError:
        return {"status": resp.status_code}
