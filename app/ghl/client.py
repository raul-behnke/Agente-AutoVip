"""Base GHL HTTP client (httpx + tenacity)."""
from __future__ import annotations

import re
import time
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app import metrics
from app.config import settings

_client: httpx.AsyncClient | None = None

# Segmentos que parecem ID (longos alfanuméricos ou só dígitos) viram {id}
# pra manter baixa cardinalidade do label `path` nas métricas.
_ID_SEG = re.compile(r"^([A-Za-z0-9]{15,}|\d+)$")


def _coarse_path(path: str) -> str:
    parts = [
        "{id}" if _ID_SEG.match(seg) else seg
        for seg in path.split("?")[0].split("/")
    ]
    return "/".join(parts)


def get_client() -> httpx.AsyncClient:
    """Lazy module-level singleton. Phase 6 will wire this through FastAPI lifespan."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.ghl_base_url,
            headers={
                "Authorization": f"Bearer {settings.ghl_pit}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.NetworkError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # 5xx (servidor) e 429 (rate limit do GHL) são transitórios → re-tenta.
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return False


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=12),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
async def request(
    method: str,
    path: str,
    *,
    version: str,
    json: Any | None = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """Make a GHL API call with per-call Version header. Raises on 4xx/5xx."""
    client = get_client()
    headers = {"Version": version}
    if json is not None:
        headers["Content-Type"] = "application/json"

    contact_id = None
    if params:
        contact_id = params.get("contactId")
    if contact_id is None and isinstance(json, dict):
        contact_id = json.get("contactId")

    t0 = time.perf_counter()
    status = None
    try:
        resp = await client.request(method, path, headers=headers, json=json, params=params)
        status = resp.status_code
        resp.raise_for_status()
        return resp
    finally:
        dt = time.perf_counter() - t0
        latency_ms = int(dt * 1000)
        coarse = _coarse_path(path)
        metrics.GHL_LATENCY.labels(path=coarse).observe(dt)
        if status is not None and status >= 400:
            metrics.GHL_ERRORS.labels(status=str(status)).inc()
        logger.info(
            "ghl_call method={} path={} status={} latency_ms={} contact_id={}",
            method, path, status, latency_ms, contact_id,
        )
