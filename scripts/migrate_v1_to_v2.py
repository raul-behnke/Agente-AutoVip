"""Migra amanda_sessions (v1 pipeline) → amanda_sessions_v2 (Agno).

Lê a tabela legada (state JSONB no formato SessionState antigo) e faz
upsert na nova via PostgresDb do Agno.

Idempotente: pode rodar várias vezes; sessions já migradas são sobrescritas
com a versão mais recente do v1.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import psycopg
from loguru import logger

# Ajusta path quando executado direto
sys.path.insert(0, ".")

from app.amanda.agent import get_db, _sqlalchemy_psycopg3_url
from app.amanda.state_schema import default_state
from app.config import settings


def _conninfo() -> str:
    url = settings.database_url
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url


def _convert_state(legacy: dict[str, Any]) -> dict[str, Any]:
    """Mapeia SessionState v1 JSONB → session_state v2 dict."""
    s = default_state()
    c = legacy.get("collected") or {}
    s["lead"]["nome"] = c.get("nome")
    s["lead"]["cidade"] = c.get("cidade")
    s["lead"]["regiao"] = legacy.get("regiao")
    s["intencao"] = c.get("intencao")
    s["veiculo_interesse"] = c.get("veiculo_interesse")
    troca = c.get("troca") or {}
    for k in ("modelo", "ano", "km", "quitado_ou_financiado",
              "fotos_solicitadas", "forma_pagamento_diferenca"):
        s["troca"][k] = troca.get(k)
    fin = c.get("financiamento") or {}
    for k in ("cpf", "data_nascimento", "entrada", "parcela_desejada", "cnh"):
        s["financiamento"][k] = fin.get(k)
    s["vista_confirmado"] = c.get("vista_confirmado")
    s["carta_credito_contemplada"] = c.get("carta_credito_contemplada")
    s["pendencias"] = list(legacy.get("pendencias") or [])
    ag = legacy.get("agendamento") or {}
    if ag:
        s["agendamento"]["tipo"] = ag.get("tipo")
        s["agendamento"]["data_hora"] = ag.get("data_hora")
        s["agendamento"]["appointment_id"] = ag.get("appointment_id")
        s["agendamento"]["confirmado"] = bool(ag.get("data_hora"))
    s["agendamento"]["oferecido"] = bool(legacy.get("agendamento_oferecido"))
    s["greeted"] = bool(legacy.get("greeted"))
    if legacy.get("handed_off") or legacy.get("terminal_reason"):
        s["handoff"]["feito"] = bool(legacy.get("handed_off"))
        s["handoff"]["motivo"] = legacy.get("terminal_reason")
        s["stage"] = "fechado"
    else:
        s["stage"] = legacy.get("stage") or "abertura"
    s["counters"]["ai_identity_asked"] = int(legacy.get("ai_identity_asked_count") or 0)
    s["counters"]["humano_solicitado"] = int(legacy.get("humano_solicitado_count") or 0)
    s["counters"]["reopen"] = int(legacy.get("reopen_count") or 0)
    return s


async def run() -> None:
    db = get_db()  # warmup + cria tabelas v2
    rows: list[tuple[str, Any]] = []
    with psycopg.connect(_conninfo()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('public.amanda_sessions') IS NOT NULL"
            )
            (exists,) = cur.fetchone()
            if not exists:
                logger.warning("legacy table amanda_sessions does not exist; nothing to migrate")
                return
            cur.execute(
                "SELECT contact_id, state, EXTRACT(EPOCH FROM updated_at)::bigint "
                "FROM amanda_sessions ORDER BY updated_at"
            )
            rows = cur.fetchall()

    logger.info("migrate: found {} sessions", len(rows))

    # Usa upsert_session do PostgresDb com AgentSession.
    from agno.session.agent import AgentSession
    migrated = 0
    for contact_id, raw_state, _ts in rows:
        if isinstance(raw_state, str):
            raw_state = json.loads(raw_state)
        new_state = _convert_state(raw_state or {})
        sess = AgentSession(
            session_id=contact_id,
            user_id=contact_id,
            agent_id="Amanda",
            session_data={"session_state": new_state},
        )
        try:
            db.upsert_session(sess)
            migrated += 1
        except Exception as e:
            logger.exception("migrate.fail contact_id={} err={}", contact_id, e)

    logger.info("migrate: done migrated={}", migrated)


if __name__ == "__main__":
    asyncio.run(run())
