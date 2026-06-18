"""Singleton da Amanda Agent — Agno-native."""
from __future__ import annotations

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat
from loguru import logger

from app.amanda.hooks import enforce_bubbles, log_tool_call
from app.amanda.instructions import INSTRUCTIONS
from app.amanda.schemas import TurnReply
from app.amanda.tools import ALL_TOOLS
from app.config import settings

_agent: Agent | None = None
_db: PostgresDb | None = None

# Modelo de chat usado pela Amanda. Fonte única — referenciada pela telemetria
# (app.pricing / app.amanda.runtime) pra casar o custo com o modelo certo.
MODEL_ID = "gpt-4.1-mini"


def _sqlalchemy_psycopg3_url(url: str) -> str:
    """Garante driver psycopg v3 (não psycopg2)."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_db() -> PostgresDb:
    global _db
    if _db is None:
        _db = PostgresDb(
            db_url=_sqlalchemy_psycopg3_url(settings.database_url),
            session_table="amanda_sessions_v2",
            memory_table="amanda_memories_v2",
        )
        logger.info("amanda.db.init table=amanda_sessions_v2")
    return _db


def get_agent() -> Agent:
    global _agent
    if _agent is not None:
        return _agent

    db = get_db()
    _agent = Agent(
        name="Amanda",
        model=OpenAIChat(id=MODEL_ID, temperature=0.6, api_key=settings.openai_api_key or None),
        db=db,
        instructions=INSTRUCTIONS,
        tools=ALL_TOOLS,
        output_schema=TurnReply,
        # Persistência de sessão + histórico
        add_history_to_context=True,
        num_history_runs=8,
        add_session_state_to_context=True,
        # We use explicit state tools in app.amanda.tools. Agno's built-in
        # update_session_state tool currently emits a schema OpenAI rejects.
        enable_agentic_state=False,
        add_datetime_to_context=True,
        # Tool governance
        tool_call_limit=10,
        max_tool_calls_from_history=20,
        compress_tool_results=True,
        # Resiliência
        retries=2,
        exponential_backoff=True,
        # Hooks
        tool_hooks=[log_tool_call],
        post_hooks=[enforce_bubbles],
    )
    logger.info("amanda.agent.init tools={} model={}", len(ALL_TOOLS), MODEL_ID)
    return _agent
