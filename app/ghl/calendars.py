"""GHL Calendars endpoints."""
from __future__ import annotations

from app.config import settings
from app.ghl.client import request

_VERSION = "2021-04-15"


async def get_free_slots(
    calendar_id: str,
    start_ms: int,
    end_ms: int,
    tz: str = "America/Sao_Paulo",
) -> dict:
    """GET /calendars/{id}/free-slots — returns dict keyed by date."""
    resp = await request(
        "GET",
        f"/calendars/{calendar_id}/free-slots",
        version=_VERSION,
        params={"startDate": start_ms, "endDate": end_ms, "timezone": tz},
    )
    return resp.json()


async def book_appointment(
    calendar_id: str,
    contact_id: str,
    start_iso: str,
    end_iso: str,
    title: str,
    notes: str = "",
) -> dict:
    """POST /calendars/events/appointments — book a slot."""
    body: dict = {
        "calendarId": calendar_id,
        "locationId": settings.ghl_location_id,
        "contactId": contact_id,
        "startTime": start_iso,
        "endTime": end_iso,
        "title": title,
        "appointmentStatus": "confirmed",
    }
    if notes:
        body["description"] = notes
    resp = await request(
        "POST",
        "/calendars/events/appointments",
        version=_VERSION,
        json=body,
    )
    return resp.json()
