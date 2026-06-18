"""Runtime do Agno Agent: orquestra webhook → agent.arun → sender."""
from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app import metrics
from app.amanda.agent import get_agent
from app.amanda.schemas import TurnReply
from app.amanda.state_schema import ensure_keys, missing_fields
from app.ghl import conversations
from app.orchestrator import concat, sender
from app.orchestrator.dispatch import execute_handoff, format_handoff_summary
from app.agent.state import SessionState  # legacy só pra montar resumo p/ handoff

active_tasks: dict[str, asyncio.Task] = {}
sending_flags: dict[str, bool] = {}

# Preço gpt-4.1-mini (USD por 1M tokens). Atualizar se trocar de modelo.
_PRICE_IN_PER_M = 0.40
_PRICE_OUT_PER_M = 1.60


def _record_llm_cost(result: Any) -> None:
    """Lê input/output tokens do RunOutput e alimenta métricas de token+custo."""
    try:
        m = getattr(result, "metrics", None)
        if m is None:
            return
        it = getattr(m, "input_tokens", None)
        ot = getattr(m, "output_tokens", None)
        if it is None and isinstance(m, dict):
            it, ot = m.get("input_tokens"), m.get("output_tokens")
        it = int(it or 0)
        ot = int(ot or 0)
        if it:
            metrics.LLM_TOKENS.labels(kind="input").inc(it)
        if ot:
            metrics.LLM_TOKENS.labels(kind="output").inc(ot)
        cost = it / 1e6 * _PRICE_IN_PER_M + ot / 1e6 * _PRICE_OUT_PER_M
        if cost:
            metrics.LLM_COST_USD.inc(cost)
    except Exception as e:
        logger.warning("runtime.cost_record_failed err={}", e)
pending_reprocess: set[str] = set()
_lock = asyncio.Lock()

REOPEN_WINDOW = timedelta(hours=24)


async def handle_inbound(contact_id: str, ad_meta: dict[str, Any] | None = None) -> None:
    """Entry-point chamado pelo webhook."""
    async with _lock:
        if sending_flags.get(contact_id):
            logger.info("handle_inbound: sending in progress queue contact_id={}", contact_id)
            pending_reprocess.add(contact_id)
            return
        existing = active_tasks.get(contact_id)
        if existing is not None and not existing.done():
            logger.info("handle_inbound: cancel prior task contact_id={}", contact_id)
            existing.cancel()
        task = asyncio.create_task(process_turn(contact_id, ad_meta=ad_meta or {}))
        active_tasks[contact_id] = task


def _last_outbound_ts(messages: list[dict]) -> datetime | None:
    for m in sorted(messages, key=lambda m: m.get("dateAdded") or "", reverse=True):
        if (m.get("direction") or "").lower() == "outbound":
            ts = m.get("dateAdded")
            if not ts:
                continue
            try:
                return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except ValueError:
                return None
    return None


def _maybe_reopen(state: dict[str, Any], messages: list[dict]) -> bool:
    handoff = (state.get("handoff") or {}).get("feito")
    if not handoff:
        return False
    last_out = _last_outbound_ts(messages)
    if last_out is None:
        return False
    if datetime.now(timezone.utc) - last_out < REOPEN_WINDOW:
        return False
    logger.info("runtime.reopen prev_motivo={}", state.get("handoff", {}).get("motivo"))
    state["handoff"] = {"feito": False, "motivo": None}
    state["agendamento"]["oferecido"] = False
    state["stage"] = "abertura"
    state["counters"]["reopen"] = state.get("counters", {}).get("reopen", 0) + 1
    state["last_asked"] = []
    return True


def _seed_ad_meta(state: dict[str, Any], ad_meta: dict[str, Any]) -> None:
    if not ad_meta:
        return
    state.setdefault("ad_meta", {}).update(ad_meta)
    veh = ad_meta.get("veiculo_interesse")
    if veh and not state.get("veiculo_interesse"):
        state["veiculo_interesse"] = str(veh).strip()


def _build_agent_input(messages: list[dict], pending: list[dict], turn_input: str) -> str:
    """Send the GHL conversation context explicitly to the model.

    Agno's built-in history is the agent run history, not the WhatsApp/GHL
    message history. Without this block the model can miss what Amanda just
    asked or what the lead already answered before the current pending batch.
    """
    history = concat.format_history(messages, pending)
    if not history:
        return turn_input
    return (
        "Histórico recente do WhatsApp:\n"
        f"{history}\n\n"
        "Mensagem atual do lead:\n"
        f"{turn_input}"
    )


def _legacy_state_for_handoff(state: dict[str, Any]) -> SessionState:
    """Converte session_state Agno (dict) pra SessionState legacy só pra
    reusar format_handoff_summary."""
    from app.agent.state import (
        Agendamento, Collected, FinanciamentoInfo, SessionState as L, TrocaInfo,
    )
    lead = state.get("lead") or {}
    troca = state.get("troca") or {}
    fin = state.get("financiamento") or {}
    ag = state.get("agendamento") or {}
    collected = Collected(
        nome=lead.get("nome"),
        cidade=lead.get("cidade"),
        veiculo_interesse=state.get("veiculo_interesse"),
        intencao=state.get("intencao"),
        troca=TrocaInfo(**{k: troca.get(k) for k in (
            "modelo", "ano", "km", "quitado_ou_financiado",
            "fotos_solicitadas", "forma_pagamento_diferenca")}),
        financiamento=FinanciamentoInfo(**{k: fin.get(k) for k in (
            "cpf", "data_nascimento", "entrada", "parcela_desejada", "cnh")}),
        vista_confirmado=state.get("vista_confirmado"),
        carta_credito_contemplada=state.get("carta_credito_contemplada"),
    )
    return L(
        collected=collected,
        agendamento=Agendamento(
            tipo=ag.get("tipo"),
            data_hora=ag.get("data_hora"),
            appointment_id=ag.get("appointment_id"),
        ) if ag.get("tipo") or ag.get("data_hora") else None,
        pendencias=state.get("pendencias") or [],
        regiao=lead.get("regiao"),
    )


async def process_turn(contact_id: str, ad_meta: dict[str, Any] | None = None) -> None:
    try:
        conversation_id = await conversations.search_conversation(contact_id)
        if conversation_id is None:
            logger.warning("runtime.no_conversation contact_id={}", contact_id)
            metrics.TURNS.labels(result="no_conversation").inc()
            return
        messages = await conversations.get_messages(conversation_id)
        pending = concat.extract_pending_inbounds(messages)
        if not pending:
            logger.info("runtime.no_pending contact_id={}", contact_id)
            metrics.TURNS.labels(result="no_pending").inc()
            return
        turn_input, _ = await concat.build_turn_input(pending)
        if not turn_input.strip():
            logger.info("runtime.empty_input contact_id={}", contact_id)
            metrics.TURNS.labels(result="empty_input").inc()
            return
        agent_input = _build_agent_input(messages, pending, turn_input)

        agent = get_agent()

        # Carrega session_state atual via Agno (db lookup) e aplica reopen/seed.
        from agno.db.base import SessionType
        db_session = agent.db.get_session(session_id=contact_id, session_type=SessionType.AGENT)
        prev_state = None
        if db_session is not None:
            sd = getattr(db_session, "session_data", None) or {}
            prev_state = sd.get("session_state") if isinstance(sd, dict) else None
        current_state = ensure_keys(prev_state)
        reopened = _maybe_reopen(current_state, messages)
        _seed_ad_meta(current_state, ad_meta or {})

        if (current_state.get("handoff") or {}).get("feito") and not reopened:
            logger.info("runtime.terminal contact_id={}", contact_id)
            metrics.TURNS.labels(result="terminal").inc()
            return

        # Ancora a última mensagem do lead no state pra o guard anti-alucinação
        # de registrar_lead_info validar valores contra o que foi realmente dito.
        current_state["_last_user_msg"] = turn_input

        # Coleta de funil já completa no início do turno → qualificado.
        if not missing_fields(current_state):
            metrics.QUALIFICADOS.inc()

        # Roda o agente. session_state_override força nosso estado merged.
        logger.info(
            "runtime.run contact_id={} input_chars={} pending_chars={} reopened={}",
            contact_id, len(agent_input), len(turn_input), reopened,
        )
        metrics.TURNS.labels(result="run").inc()
        _t0 = time.perf_counter()
        result = await agent.arun(
            input=agent_input,
            session_id=contact_id,
            user_id=contact_id,
            session_state=current_state,
        )
        metrics.LLM_LATENCY.observe(time.perf_counter() - _t0)
        _record_llm_cost(result)

        reply: TurnReply | None = result.content if isinstance(result.content, TurnReply) else None
        if reply is None or not reply.bubbles:
            blob = f"{getattr(result, 'status', '')} {getattr(result, 'content', '')}".lower()
            if "insufficient_quota" in blob or "exceeded your current quota" in blob:
                logger.error(
                    "runtime.openai_quota_exceeded contact_id={} — repor billing OpenAI", contact_id
                )
                metrics.OPENAI_QUOTA_ERRORS.inc()
            else:
                logger.warning("runtime.empty_reply contact_id={}", contact_id)
            metrics.TURNS.labels(result="empty_reply").inc()
            return

        blocks = [b.text for b in reply.bubbles]

        # Side-effects de handoff: se a tool acionar_handoff foi chamada,
        # session_state.handoff.feito == True após o run.
        try:
            post_state = await agent.aget_session_state(session_id=contact_id) or current_state
        except Exception:
            post_state = current_state
        handoff = (post_state.get("handoff") or {})
        if handoff.get("feito"):
            motivo = handoff.get("motivo") or "coleta_completa"
            metrics.HANDOFF.labels(motivo=motivo).inc()
            try:
                legacy = _legacy_state_for_handoff(post_state)
                await execute_handoff(contact_id, legacy, motivo)
            except Exception as e:
                logger.exception("runtime.handoff_exec_failed err={}", e)

        sending_flags[contact_id] = True
        await asyncio.shield(sender.send_blocks(contact_id, blocks))

    except asyncio.CancelledError:
        logger.info("runtime.cancelled contact_id={}", contact_id)
        raise
    except Exception as e:
        msg = str(e).lower()
        if "insufficient_quota" in msg or "exceeded your current quota" in msg:
            logger.error("runtime.openai_quota_exceeded contact_id={} — repor billing OpenAI", contact_id)
            metrics.OPENAI_QUOTA_ERRORS.inc()
        else:
            logger.error(
                "runtime.error contact_id={} err={}\n{}",
                contact_id, e, traceback.format_exc(),
            )
        metrics.TURNS.labels(result="error").inc()
    finally:
        sending_flags[contact_id] = False
        current = asyncio.current_task()
        if active_tasks.get(contact_id) is current:
            active_tasks.pop(contact_id, None)
        if contact_id in pending_reprocess:
            pending_reprocess.discard(contact_id)
            logger.info("runtime.reprocess_pending contact_id={}", contact_id)
            asyncio.create_task(handle_inbound(contact_id))
