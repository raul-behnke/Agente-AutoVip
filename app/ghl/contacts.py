"""GHL Contacts endpoints (notes, tags)."""
from __future__ import annotations

from app.ghl.client import request

_VERSION = "2021-07-28"


async def add_note(contact_id: str, body: str) -> dict:
    """POST /contacts/{id}/notes — create a contact note."""
    resp = await request(
        "POST",
        f"/contacts/{contact_id}/notes",
        version=_VERSION,
        json={"body": body},
    )
    return resp.json()


async def update_custom_fields(contact_id: str, fields: list[dict]) -> dict:
    """PUT /contacts/{id} — atualiza custom fields do contato.
    `fields`: lista de {"id": <fieldId>, "value": <valor>}."""
    resp = await request(
        "PUT",
        f"/contacts/{contact_id}",
        version=_VERSION,
        json={"customFields": fields},
    )
    try:
        return resp.json()
    except ValueError:
        return {"status": resp.status_code}


async def add_handoff_note(
    contact_id: str,
    summary: str,
    mentioned_user_id: str,
    mentioned_name: str = "Ramon",
) -> dict:
    """Replacement for the dead InternalComment concept.

    Writes a contact note tagging the human owner via plain-text mention plus userId.
    """
    body = f"@{mentioned_name} (userId:{mentioned_user_id})\n\n{summary}"
    return await add_note(contact_id, body)


async def remove_tag(contact_id: str, tag: str | list[str]) -> dict:
    """DELETE /contacts/{id}/tags — remove uma ou mais tags do contato."""
    tags = [tag] if isinstance(tag, str) else list(tag)
    resp = await request(
        "DELETE",
        f"/contacts/{contact_id}/tags",
        version=_VERSION,
        json={"tags": tags},
    )
    try:
        return resp.json()
    except ValueError:
        return {"status": resp.status_code}
