"""Gravação de telemetria persistida (llm_calls + agent_events).

Helpers async tolerantes a falha: qualquer erro de DB é logado e engolido —
telemetria NUNCA derruba o atendimento do lead.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import insert
from loguru import logger

from app.telemetry.db import (
    AGENT_SLUG,
    CLIENT_SLUG,
    SCHEMA_VERSION,
    agent_events,
    get_engine,
    llm_calls,
)


def _new_event_id() -> str:
    """UUID4 — idempotência: o Hub deduplica por este campo."""
    return str(uuid.uuid4())


def _envelope() -> dict[str, Any]:
    return {
        "event_id": _new_event_id(),
        "schema_version": SCHEMA_VERSION,
        "client": CLIENT_SLUG,
        "agent": AGENT_SLUG,
    }


def _insert_sync(table, values: dict[str, Any]) -> None:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(insert(table).values(**values))


async def record_llm_call(
    *,
    model: str,
    kind: str = "chat",
    contact_id: str | None = None,
    conversation_id: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int | None = None,
    audio_seconds: float | None = None,
    cost_usd: float = 0.0,
    cost_brl: float = 0.0,
    usd_brl_rate: float | None = None,
    pricing_version: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Persiste uma chamada de modelo (chat ou whisper) com atribuição.
    Carrega o envelope canônico → vira o evento LLM_CALL/WHISPER no Hub."""
    if total_tokens is None:
        total_tokens = int(input_tokens) + int(output_tokens)
    values: dict[str, Any] = {
        **_envelope(),
        "model": model,
        "kind": kind,
        "contact_id": contact_id,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "request_id": request_id,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "audio_seconds": audio_seconds,
        "cost_usd": round(float(cost_usd or 0.0), 8),
        "cost_brl": round(float(cost_brl or 0.0), 8),
        "usd_brl_rate": usd_brl_rate,
        "pricing_version": pricing_version,
        "latency_ms": latency_ms,
    }
    try:
        await asyncio.to_thread(_insert_sync, llm_calls, values)
    except Exception as e:
        logger.warning("telemetry.llm_call_persist_failed model={} err={}", model, e)

    # Também emite o evento canônico no event log (agent_events) — fonte única
    # do /export pro Hub. payload segue CONTRATO §3.1 (LLM_CALL) / §3.2 (Whisper).
    if kind == "whisper":
        event_type = "WHISPER_TRANSCRIPTION"
        payload = {
            "model": model,
            "audio_seconds": audio_seconds,
            "cost_usd": round(float(cost_usd or 0.0), 8),
            "cost_brl": round(float(cost_brl or 0.0), 8),
            "usd_brl_rate": usd_brl_rate,
            "pricing_version": pricing_version,
            "latency_ms": latency_ms,
        }
    else:
        event_type = "LLM_CALL"
        payload = {
            "component": "agent",
            "model": model,
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "total_tokens": int(total_tokens or 0),
            "reasoning_tokens": None,
            "cost_usd": round(float(cost_usd or 0.0), 8),
            "cost_brl": round(float(cost_brl or 0.0), 8),
            "usd_brl_rate": usd_brl_rate,
            "pricing_version": pricing_version,
            "request_id": request_id,
            "latency_ms": latency_ms,
        }
    await emit_event(
        event_type,
        contact_id=contact_id,
        conversation_id=conversation_id,
        session_id=session_id,
        payload=payload,
        cost_usd=cost_usd,
        cost_brl=cost_brl,
    )


async def emit_event(
    event_type: str,
    *,
    contact_id: str | None = None,
    conversation_id: str | None = None,
    session_id: str | None = None,
    payload: dict[str, Any] | None = None,
    cost_usd: float | None = None,
    cost_brl: float | None = None,
) -> None:
    """Grava uma linha no event log append-only (envelope canônico)."""
    values: dict[str, Any] = {
        **_envelope(),
        "event_type": event_type,
        "contact_id": contact_id,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "payload": payload or {},
        "cost_usd": round(float(cost_usd), 8) if cost_usd is not None else None,
        "cost_brl": round(float(cost_brl), 8) if cost_brl is not None else None,
    }
    try:
        await asyncio.to_thread(_insert_sync, agent_events, values)
    except Exception as e:
        logger.warning("telemetry.event_persist_failed type={} err={}", event_type, e)
