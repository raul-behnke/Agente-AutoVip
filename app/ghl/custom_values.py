"""GHL Custom Values endpoint."""
from __future__ import annotations

from app.config import settings
from app.ghl.client import request

_VERSION = "2021-07-28"


async def get_custom_value(value_id: str) -> str:
    """GET /locations/{locationId}/customValues/{id} — return raw `value` string."""
    resp = await request(
        "GET",
        f"/locations/{settings.ghl_location_id}/customValues/{value_id}",
        version=_VERSION,
    )
    data = resp.json()
    cv = data.get("customValue") or {}
    return cv.get("value", "") or ""
