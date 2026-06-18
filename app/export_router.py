"""Endpoint /export/events — PULL HTTP incremental para o ZOI Performance Hub.

Contrato (CONTRATO_EVENTOS_CANONICO.md §5): o Hub puxa `agent_events` por
cursor (`since` = último id ingerido), autenticando via HMAC-SHA256 do cursor
com o `ZOI_EXPORT_SECRET` (secret DEDICADO, distinto do webhook). Resposta no
envelope canônico com idempotência por `event_id`.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.telemetry.db import agent_events, get_engine

router = APIRouter()

_MAX_LIMIT = 1000


def _expected_sig(since: str) -> str:
    """HMAC-SHA256(secret, since) em hex — assina o cursor."""
    return hmac.new(
        settings.zoi_export_secret.encode("utf-8"),
        since.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _to_iso_utc(dt: Any) -> str | None:
    if dt is None:
        return None
    try:
        return dt.astimezone().isoformat()
    except Exception:
        return str(dt)


def _fetch_sync(since_id: int, limit: int) -> list[dict[str, Any]]:
    eng = get_engine()
    cols = agent_events.c
    stmt = (
        select(
            cols.id, cols.event_id, cols.schema_version, cols.client, cols.agent,
            cols.event_type, cols.contact_id, cols.conversation_id, cols.ts,
            cols.payload, cols.cost_usd, cols.cost_brl,
        )
        .where(cols.id > since_id)
        .order_by(cols.id.asc())
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    with eng.connect() as conn:
        for r in conn.execute(stmt):
            payload = dict(r.payload or {})
            if r.cost_usd is not None and "cost_usd" not in payload:
                payload["cost_usd"] = float(r.cost_usd)
            if r.cost_brl is not None and "cost_brl" not in payload:
                payload["cost_brl"] = float(r.cost_brl)
            out.append({
                "_id": int(r.id),  # cursor interno (não faz parte do envelope)
                "event_id": r.event_id,
                "schema_version": r.schema_version,
                "event_type": r.event_type,
                "client": r.client,
                "agent": r.agent,
                "contact_id": r.contact_id,
                "conversation_id": r.conversation_id or r.contact_id,
                "occurred_at": _to_iso_utc(r.ts),
                "payload": payload,
            })
    return out


@router.get("/export/events")
async def export_events(
    since: str = Query("0", description="Cursor = último id ingerido"),
    sig: str = Query("", description="HMAC-SHA256(secret, since) hex"),
    limit: int = Query(500, ge=1, le=_MAX_LIMIT),
) -> dict[str, Any]:
    import asyncio

    if not settings.zoi_export_secret:
        raise HTTPException(status_code=503, detail="export disabled")
    if not sig or not hmac.compare_digest(sig, _expected_sig(since)):
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        since_id = int(since)
    except ValueError:
        raise HTTPException(status_code=400, detail="since must be an integer cursor")

    rows = await asyncio.to_thread(_fetch_sync, since_id, limit)
    next_cursor = str(rows[-1]["_id"]) if rows else since
    events = [{k: v for k, v in r.items() if k != "_id"} for r in rows]
    logger.info("export.events since={} n={} next={}", since, len(events), next_cursor)
    return {"events": events, "next_cursor": next_cursor}
