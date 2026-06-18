"""Engine SQLAlchemy + DDL das tabelas de telemetria.

Engine síncrono dedicado (separado do que o Agno usa internamente). As
escritas são pequenas (uma linha por turno/evento) e executadas via
`asyncio.to_thread` pelos callers async, pra não bloquear o event loop.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from loguru import logger

from app.config import settings

_engine: Engine | None = None
_bootstrapped = False

metadata = MetaData()

# Slugs canônicos da frota (CONTRATO_EVENTOS_CANONICO.md §2).
CLIENT_SLUG = "autovip"
AGENT_SLUG = "amanda-autovip"
SCHEMA_VERSION = 1

# Detalhe financeiro por chamada de modelo (chat ou whisper).
# É a fonte do evento canônico LLM_CALL / WHISPER_TRANSCRIPTION exportado ao Hub
# → carrega o envelope (event_id/schema_version/client/agent).
llm_calls = Table(
    "llm_calls",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    # Envelope canônico
    Column("event_id", String(36), unique=True, nullable=False),
    Column("schema_version", Integer, nullable=False, server_default="1"),
    Column("client", String(32), nullable=False, server_default=CLIENT_SLUG),
    Column("agent", String(64), nullable=False, server_default=AGENT_SLUG),
    Column("ts", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("contact_id", String(128), index=True),
    Column("conversation_id", String(128), index=True),
    Column("session_id", String(128), index=True),
    Column("model", String(64), nullable=False),
    Column("kind", String(16), nullable=False, server_default="chat"),  # chat | whisper
    Column("request_id", String(128)),
    Column("input_tokens", Integer, server_default="0"),
    Column("output_tokens", Integer, server_default="0"),
    Column("total_tokens", Integer, server_default="0"),
    Column("audio_seconds", Numeric(12, 3)),
    Column("cost_usd", Numeric(14, 8), server_default="0"),
    Column("cost_brl", Numeric(14, 8), server_default="0"),
    Column("usd_brl_rate", Numeric(10, 4)),
    Column("pricing_version", String(32)),
    Column("latency_ms", Integer),
)

# Preço por modelo, versionado por vigência. Substitui o hardcode do runtime.
pricing = Table(
    "pricing",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("model", String(64), nullable=False, index=True),
    Column("price_in_per_m", Numeric(12, 6), server_default="0"),   # USD / 1M tokens input
    Column("price_out_per_m", Numeric(12, 6), server_default="0"),  # USD / 1M tokens output
    Column("price_per_minute", Numeric(12, 6), server_default="0"), # USD / min (whisper)
    Column("usd_brl_rate", Numeric(10, 4), nullable=False, server_default="5.40"),  # câmbio versionado
    Column("currency", String(8), nullable=False, server_default="USD"),
    Column("version", String(32), nullable=False),
    Column("valid_from", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("valid_to", DateTime(timezone=True)),
)

# Event log append-only (timeline operacional/comercial). Envelope canônico.
agent_events = Table(
    "agent_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    # Envelope canônico (CONTRATO_EVENTOS_CANONICO.md §2)
    Column("event_id", String(36), unique=True, nullable=False),
    Column("schema_version", Integer, nullable=False, server_default="1"),
    Column("client", String(32), nullable=False, server_default=CLIENT_SLUG),
    Column("agent", String(64), nullable=False, server_default=AGENT_SLUG),
    Column("ts", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("event_type", String(48), nullable=False, index=True),
    Column("contact_id", String(128), index=True),
    Column("conversation_id", String(128), index=True),
    Column("session_id", String(128), index=True),
    Column("payload", JSONB),
    Column("cost_usd", Numeric(14, 8)),
    Column("cost_brl", Numeric(14, 8)),
)


def _sqlalchemy_psycopg3_url(url: str) -> str:
    """Garante driver psycopg v3 (mesma normalização de app.amanda.agent)."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            _sqlalchemy_psycopg3_url(settings.database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
    return _engine


def init_telemetry_schema() -> None:
    """Cria as tabelas se ainda não existirem. Idempotente."""
    global _bootstrapped
    if _bootstrapped:
        return
    try:
        metadata.create_all(get_engine())
        _bootstrapped = True
        logger.info("telemetry.schema.ready tables=llm_calls,agent_events")
    except Exception as e:
        logger.error("telemetry.schema.init_failed err={}", e)
