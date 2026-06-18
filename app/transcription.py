"""Whisper audio transcription."""
from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx
from loguru import logger
from openai import AsyncOpenAI

from app import pricing
from app.config import settings
from app.telemetry import record_llm_call

_WHISPER_MODEL = "whisper-1"
_client: AsyncOpenAI | None = None
_cache: dict[str, str] = {}


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if path else ""
    if not name or "." not in name:
        return "audio.ogg"
    return name


async def transcribe(
    audio_url: str,
    *,
    contact_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    """Download audio from URL and transcribe via Whisper. Cached per-process.

    Custo é contabilizado (Prometheus + `llm_calls`) com atribuição por
    conversa/lead. Usa `verbose_json` pra obter a duração faturável do áudio.
    """
    if audio_url in _cache:
        return _cache[audio_url]

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=30.0) as http:
        r = await http.get(audio_url)
        r.raise_for_status()
        audio_bytes = r.content

    filename = _filename_from_url(audio_url)

    try:
        client = _get_client()
        resp = await client.audio.transcriptions.create(
            model=_WHISPER_MODEL,
            file=(filename, audio_bytes),
            language="pt",
            response_format="verbose_json",
        )
        text = resp.text
        audio_seconds = float(getattr(resp, "duration", 0.0) or 0.0)
    except Exception as e:
        logger.error(f"whisper transcribe failed url={audio_url} err={e}")
        raise

    dt_ms = int((time.monotonic() - t0) * 1000)
    cost_usd, cost_brl, usd_brl_rate, pricing_version = pricing.cost_whisper(
        _WHISPER_MODEL, audio_seconds
    )
    logger.info(
        "whisper ok url={} latency_ms={} chars={} audio_s={} cost_usd={} cost_brl={}",
        audio_url, dt_ms, len(text), audio_seconds, round(cost_usd, 6), round(cost_brl, 6),
    )
    if cost_usd:
        from app import metrics
        metrics.LLM_COST_USD.inc(cost_usd)
    await record_llm_call(
        model=_WHISPER_MODEL,
        kind="whisper",
        contact_id=contact_id,
        conversation_id=conversation_id,
        audio_seconds=audio_seconds,
        cost_usd=cost_usd,
        cost_brl=cost_brl,
        usd_brl_rate=usd_brl_rate,
        pricing_version=pricing_version,
        latency_ms=dt_ms,
    )
    _cache[audio_url] = text
    return text
