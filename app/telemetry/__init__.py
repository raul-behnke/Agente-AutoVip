"""Telemetria persistida para o ZOI Performance Hub.

Tabelas relacionais próprias (`llm_calls`, `agent_events`) no mesmo Postgres
do agente — NÃO tocam no schema gerido pelo Agno (`amanda_sessions_v2`).
São a fonte de verdade histórica/financeira lida pelo coletor do Hub.
Prometheus (`app.metrics`) permanece para tempo real.
"""
from __future__ import annotations

from app.telemetry.events import emit_event, record_llm_call
from app.telemetry.db import init_telemetry_schema

__all__ = ["emit_event", "record_llm_call", "init_telemetry_schema"]
