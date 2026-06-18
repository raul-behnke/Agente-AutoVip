"""Inbound webhook endpoint."""
from __future__ import annotations

import asyncio
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app import metrics
from app.config import settings
from app.amanda.runtime import handle_inbound

router = APIRouter()

# GHL usa as duas grafias da tag de gate; aceitar ambas pra não bloquear lead.
_GATE_TAGS = {"agente-ia", "agent-ia"}


def _parse_tags(raw: Any) -> set[str]:
    """Normaliza tags do payload (lista ou CSV) → set lowercase."""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        items = raw.split(",")
    else:
        return set()
    return {str(t).strip().lower() for t in items if str(t).strip()}


def _extract_contact_id(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    cid = payload.get("contact_id") or payload.get("contactId")
    if cid:
        return cid
    contact = payload.get("contact")
    if isinstance(contact, dict):
        cid = contact.get("id")
        if cid:
            return cid
    custom = payload.get("customData")
    if isinstance(custom, dict):
        cid = custom.get("contact_id") or custom.get("contactId")
        if cid:
            return cid
    return None


@router.post("/webhook/inbound/{token}")
async def inbound(token: str, request: Request) -> dict[str, Any]:
    if not secrets.compare_digest(token, settings.webhook_token):
        raise HTTPException(status_code=401, detail="invalid token")

    try:
        payload = await request.json()
    except Exception as e:
        logger.warning("webhook: invalid json err={}", e)
        return {"ok": False, "reason": "invalid json"}

    contact_id = _extract_contact_id(payload if isinstance(payload, dict) else {})
    keys = list(payload.keys()) if isinstance(payload, dict) else []
    logger.info("webhook_inbound contact_id={} payload_keys={}", contact_id, keys)

    if not contact_id:
        logger.warning("webhook: no contact_id in payload keys={}", keys)
        return {"ok": False, "reason": "no contact_id"}

    # Gate de tag `agente-ia`: opt-in/out por contato. Se o payload trouxer
    # tags e a tag de gate NÃO estiver presente, não processa (noop 200).
    # Sem campo `tags` no payload → não bloqueia (ex.: webhook mínimo/teste).
    if isinstance(payload, dict) and "tags" in payload:
        tags = _parse_tags(payload.get("tags"))
        if not (_GATE_TAGS & tags):
            logger.info("webhook.gate_skip contact_id={} tags={}", contact_id, sorted(tags))
            metrics.TURNS.labels(result="skipped_no_tag").inc()
            return {"ok": True, "skipped": "no agente-ia tag"}

    # Extrai metadados do anúncio (custom fields que GHL injeta no payload)
    ad_meta = {
        "veiculo_interesse": (
            payload.get("VEÍCULO DE INTERESSE")
            or payload.get("Modelo do Veículo")
            or None
        ),
        "ano": payload.get("ANO VEÍCULO DE INTERESSE") or payload.get("Ano do Veículo"),
    }
    ad_meta = {k: v for k, v in ad_meta.items() if v}

    asyncio.create_task(handle_inbound(contact_id, ad_meta=ad_meta))
    return {"ok": True}


@router.post("/sessions/{contact_id}/abandon/{token}")
async def abandon(contact_id: str, token: str) -> dict[str, Any]:
    """Encerra a sessão do contato (CRM-side): marca handoff terminal pra a
    Amanda parar de responder. Idempotente. Protegido pelo webhook_token."""
    if not secrets.compare_digest(token, settings.webhook_token):
        raise HTTPException(status_code=401, detail="invalid token")
    from app.amanda.agent import get_agent

    agent = get_agent()
    try:
        await agent.aupdate_session_state(
            {"handoff": {"feito": True, "motivo": "abandonado"}, "stage": "fechado"},
            session_id=contact_id,
        )
        logger.info("session.abandon contact_id={}", contact_id)
        metrics.HANDOFF.labels(motivo="abandonado").inc()
        from app.telemetry import emit_event
        await emit_event(
            "CONVERSATION_ABANDONED",
            contact_id=contact_id,
            session_id=contact_id,
            payload={"motivo": "abandonado"},
        )
        return {"ok": True, "contact_id": contact_id}
    except Exception as e:
        logger.warning("session.abandon failed contact_id={} err={}", contact_id, e)
        return {"ok": False, "reason": "abandon failed"}
