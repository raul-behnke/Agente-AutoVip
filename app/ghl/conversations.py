"""GHL Conversations endpoints."""
from __future__ import annotations

import httpx
from loguru import logger

from app.config import settings
from app.ghl.client import request

_VERSION = "2021-04-15"


async def search_conversation(contact_id: str) -> str | None:
    """GET /conversations/search — return first conversation id for contact, or None.

    Um 400 "Contact not found" significa que o contactId não existe nesta
    location (contato estrangeiro/deletado, ou webhook de outra subconta).
    Tratamos como ausência de conversa (None), sem estourar exceção — evita
    poluir o log com `runtime.error` para tráfego que não é nosso.
    """
    try:
        resp = await request(
            "GET",
            "/conversations/search",
            version=_VERSION,
            params={
                "locationId": settings.ghl_location_id,
                "contactId": contact_id,
                "limit": 1,
                "sortBy": "last_message_date",
                "sort": "desc",
            },
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            logger.info(
                "search_conversation.contact_not_found contact_id={}", contact_id
            )
            return None
        raise
    data = resp.json()
    convs = data.get("conversations") or []
    if not convs:
        return None
    return convs[0].get("id")


async def get_messages(conversation_id: str, limit: int = 50) -> list[dict]:
    """GET /conversations/{id}/messages — return raw `messages` list."""
    resp = await request(
        "GET",
        f"/conversations/{conversation_id}/messages",
        version=_VERSION,
        params={"limit": limit},
    )
    data = resp.json()
    # Response shape: { "messages": { "messages": [...] } } OR { "messages": [...] }
    msgs = data.get("messages")
    if isinstance(msgs, dict):
        return msgs.get("messages") or []
    if isinstance(msgs, list):
        return msgs
    return []


async def send_sms(contact_id: str, message: str) -> dict:
    """POST /conversations/messages — SMS send (no userId per corrections)."""
    resp = await request(
        "POST",
        "/conversations/messages",
        version=_VERSION,
        json={"type": "SMS", "contactId": contact_id, "message": message},
    )
    return resp.json()
