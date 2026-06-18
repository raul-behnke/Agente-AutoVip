"""Lookup de preço por modelo (tabela `pricing`), com seed e cache.

Substitui o preço hardcoded de `app/amanda/runtime.py`. Cada custo gravado
em `llm_calls` carrega a `pricing_version` usada → custo histórico reprodutível
mesmo após reajuste de preço.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy import insert, select
from loguru import logger

from app.telemetry.db import get_engine, pricing

# Câmbio padrão da frota (CONTRATO_EVENTOS_CANONICO.md §6). Versionado na tabela.
_DEFAULT_USD_BRL = 5.40

# Defaults oficiais (USD). Seed inicial; ajustar na tabela sem deploy.
# gpt-4.1-mini: $0.40 / $1.60 por 1M (input/output). whisper-1: $0.006 / min.
_SEED: tuple[dict[str, Any], ...] = (
    {
        "model": "gpt-4.1-mini",
        "price_in_per_m": "0.40",
        "price_out_per_m": "1.60",
        "price_per_minute": "0",
        "usd_brl_rate": str(_DEFAULT_USD_BRL),
        "version": "2025-01-baseline",
    },
    {
        "model": "whisper-1",
        "price_in_per_m": "0",
        "price_out_per_m": "0",
        "price_per_minute": "0.006",
        "usd_brl_rate": str(_DEFAULT_USD_BRL),
        "version": "2025-01-baseline",
    },
)

# cache em memória: model → dict(price_in, price_out, price_min, version)
_CACHE: dict[str, dict[str, Any]] | None = None


def seed_pricing() -> None:
    """Insere os defaults para modelos ainda sem linha vigente. Idempotente."""
    eng = get_engine()
    try:
        with eng.begin() as conn:
            existing = {
                r[0]
                for r in conn.execute(select(pricing.c.model).distinct()).fetchall()
            }
            to_add = [row for row in _SEED if row["model"] not in existing]
            if to_add:
                conn.execute(insert(pricing), to_add)
                logger.info("pricing.seeded models={}", [r["model"] for r in to_add])
    except Exception as e:
        logger.error("pricing.seed_failed err={}", e)


def _load_cache() -> dict[str, dict[str, Any]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    cache: dict[str, dict[str, Any]] = {}
    try:
        eng = get_engine()
        with eng.connect() as conn:
            # Última linha vigente (valid_to NULL) por modelo, mais recente primeiro.
            rows = conn.execute(
                select(
                    pricing.c.model,
                    pricing.c.price_in_per_m,
                    pricing.c.price_out_per_m,
                    pricing.c.price_per_minute,
                    pricing.c.usd_brl_rate,
                    pricing.c.version,
                    pricing.c.valid_from,
                )
                .where(pricing.c.valid_to.is_(None))
                .order_by(pricing.c.valid_from.desc())
            ).fetchall()
        for r in rows:
            if r.model not in cache:
                cache[r.model] = {
                    "price_in_per_m": float(r.price_in_per_m or 0),
                    "price_out_per_m": float(r.price_out_per_m or 0),
                    "price_per_minute": float(r.price_per_minute or 0),
                    "usd_brl_rate": float(r.usd_brl_rate or _DEFAULT_USD_BRL),
                    "version": r.version,
                }
    except Exception as e:
        logger.error("pricing.load_failed err={}", e)
    _CACHE = cache
    return cache


def refresh_cache() -> None:
    global _CACHE
    _CACHE = None


# Fallback se o modelo não estiver na tabela (mantém comportamento atual).
_FALLBACK = {
    "gpt-4.1-mini": {"price_in_per_m": 0.40, "price_out_per_m": 1.60, "price_per_minute": 0.0, "usd_brl_rate": _DEFAULT_USD_BRL, "version": "fallback"},
    "whisper-1": {"price_in_per_m": 0.0, "price_out_per_m": 0.0, "price_per_minute": 0.006, "usd_brl_rate": _DEFAULT_USD_BRL, "version": "fallback"},
}


def get_pricing(model: str) -> dict[str, Any]:
    """Retorna {price_in_per_m, price_out_per_m, price_per_minute, usd_brl_rate, version}."""
    cache = _load_cache()
    if model in cache:
        return cache[model]
    return _FALLBACK.get(
        model,
        {"price_in_per_m": 0.0, "price_out_per_m": 0.0, "price_per_minute": 0.0,
         "usd_brl_rate": _DEFAULT_USD_BRL, "version": "unknown"},
    )


def cost_chat(model: str, input_tokens: int, output_tokens: int) -> tuple[float, float, float, str]:
    """Custo de uma chamada de chat.
    Retorna (cost_usd, cost_brl, usd_brl_rate, pricing_version)."""
    p = get_pricing(model)
    rate = p["usd_brl_rate"]
    cost_usd = input_tokens / 1e6 * p["price_in_per_m"] + output_tokens / 1e6 * p["price_out_per_m"]
    return cost_usd, cost_usd * rate, rate, p["version"]


def cost_whisper(model: str, audio_seconds: float) -> tuple[float, float, float, str]:
    """Custo de uma transcrição (Whisper cobra por minuto faturável, arredondado
    pra cima — CONTRATO §6). Retorna (cost_usd, cost_brl, usd_brl_rate, pricing_version)."""
    p = get_pricing(model)
    rate = p["usd_brl_rate"]
    minutes = math.ceil((audio_seconds or 0) / 60.0)
    cost_usd = minutes * p["price_per_minute"]
    return cost_usd, cost_usd * rate, rate, p["version"]
