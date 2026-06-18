"""Runtime do Agno Agent: orquestra webhook → agent.arun → sender."""
from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app import metrics
from app.amanda.agent import get_agent, MODEL_ID
from app.amanda.schemas import TurnReply
from app.amanda.state_schema import ensure_keys, missing_fields
from app.ghl import conversations
from app.orchestrator import concat, sender
from app.orchestrator.dispatch import execute_handoff, format_handoff_summary
from app.agent.state import SessionState  # legacy só pra montar resumo p/ handoff
from app import pricing
from app.telemetry import emit_event, record_llm_call

active_tasks: dict[str, asyncio.Task] = {}
sending_flags: dict[str, bool] = {}


def _extract_tokens(result: Any) -> tuple[int, int]:
    """Lê input/output tokens do RunOutput do Agno (objeto ou dict)."""
    m = getattr(result, "metrics", None)
    if m is None:
        return 0, 0
    it = getattr(m, "input_tokens", None)
    ot = getattr(m, "output_tokens", None)
    if it is None and isinstance(m, dict):
        it, ot = m.get("input_tokens"), m.get("output_tokens")
    return int(it or 0), int(ot or 0)


def _extract_request_id(result: Any) -> str | None:
    """Best-effort: tenta achar o request_id da OpenAI no RunOutput do Agno.
    Se o Agno não expuser, retorna None (campo fica nulo em llm_calls)."""
    for attr in ("request_id", "response_id", "id"):
        v = getattr(result, attr, None)
        if v:
            return str(v)
    m = getattr(result, "metrics", None)
    if isinstance(m, dict):
        return m.get("request_id") or m.get("response_id")
    return getattr(m, "request_id", None)


async def _record_llm_cost(
    result: Any,
    *,
    contact_id: str | None = None,
    conversation_id: str | None = None,
    session_id: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Alimenta métricas Prometheus (tempo real) E persiste a chamada em
    `llm_calls` com atribuição por conversa/lead (histórico financeiro)."""
    try:
        it, ot = _extract_tokens(result)
        if it:
            metrics.LLM_TOKENS.labels(kind="input").inc(it)
        if ot:
            metrics.LLM_TOKENS.labels(kind="output").inc(ot)
        cost_usd, cost_brl, usd_brl_rate, pricing_version = pricing.cost_chat(MODEL_ID, it, ot)
        if cost_usd:
            metrics.LLM_COST_USD.inc(cost_usd)
        await record_llm_call(
            model=MODEL_ID,
            kind="chat",
            contact_id=contact_id,
            conversation_id=conversation_id,
            session_id=session_id,
            request_id=_extract_request_id(result),
            input_tokens=it,
            output_tokens=ot,
            total_tokens=it + ot,
            cost_usd=cost_usd,
            cost_brl=cost_brl,
            usd_brl_rate=usd_brl_rate,
            pricing_version=pricing_version,
            latency_ms=latency_ms,
        )
    except Exception as e:
        logger.warning("runtime.cost_record_failed err={}", e)


# Fuso Brasil (sem DST atualmente) pra montar janela do appointment.
_SP_TZ = timezone(timedelta(hours=-3))


def _appt_window(data_hora: Any) -> tuple[str | None, str | None]:
    """Converte data_hora (ISO, possivelmente sem fuso) em (start_iso, end_iso)
    com fuso America/Sao_Paulo; duração de 1h."""
    s = str(data_hora or "").strip().replace("Z", "")
    if not s:
        return None, None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_SP_TZ)
    return dt.isoformat(), (dt + timedelta(hours=1)).isoformat()


async def _maybe_book_appointment(agent, contact_id: str, state: dict[str, Any]) -> None:
    """Reserva a visita no calendário GHL quando o lead confirmou dia/hora.
    Idempotente: só reserva se confirmado + data_hora + sem appointment_id."""
    ag = state.get("agendamento") or {}
    if not (ag.get("confirmado") and ag.get("data_hora") and not ag.get("appointment_id")):
        return
    from app.config import settings
    from app.ghl import calendars

    tipo = ag.get("tipo") or "presencial"
    cal_id = settings.cal_video_id if tipo == "video" else settings.cal_presencial_id
    if not cal_id:
        logger.warning("runtime.book_skip no_calendar_id tipo={}", tipo)
        return
    start_iso, end_iso = _appt_window(ag.get("data_hora"))
    if not start_iso:
        logger.warning("runtime.book_skip bad_datetime data_hora={}", ag.get("data_hora"))
        return
    veh = state.get("veiculo_interesse") or "veículo"
    try:
        resp = await calendars.book_appointment(
            cal_id, contact_id, start_iso, end_iso,
            title=f"Visita Auto Vip - {veh}",
            notes="Agendado pela Amanda (IA).",
        )
        appt_id = resp.get("id") or (resp.get("appointment") or {}).get("id")
        if appt_id:
            ag["appointment_id"] = appt_id
            await agent.aupdate_session_state({"agendamento": ag}, session_id=contact_id)
            logger.info(
                "runtime.appointment_booked contact_id={} appt_id={} when={} tipo={}",
                contact_id, appt_id, start_iso, tipo,
            )
            await emit_event(
                "APPOINTMENT_CREATED",
                contact_id=contact_id,
                conversation_id=state.get("conversation_id"),
                session_id=contact_id,
                payload={"tipo": tipo, "data_hora": ag.get("data_hora"),
                         "appointment_id": appt_id, "calendar_id": cal_id},
            )
        else:
            logger.warning("runtime.book_no_id resp_keys={}", list(resp.keys()))
    except Exception as e:
        logger.exception("runtime.book_failed contact_id={} err={}", contact_id, e)
async def _link_opportunity(
    contact_id: str, conversation_id: str | None, state: dict[str, Any], motivo: str
) -> None:
    """Fase 3: liga o atendimento da IA a uma oportunidade do pipeline GHL.

    Best-effort e idempotente: pula se pipeline não configurado; reusa a
    oportunidade existente do contato; cria uma nova se não houver. Persiste
    `opportunity_id` no state e emite OPPORTUNITY_LINKED."""
    from app.config import settings
    if not settings.ghl_pipeline_id:
        return  # camada comercial desativada (sem pipeline configurado)
    from app.ghl import opportunities

    try:
        opp_id = state.get("opportunity_id")
        created = False
        if not opp_id:
            opp_id = await opportunities.search_opportunity(contact_id)
        if not opp_id:
            lead = state.get("lead") or {}
            veh = state.get("veiculo_interesse") or "veículo"
            nome = lead.get("nome") or contact_id
            resp = await opportunities.create_opportunity(
                contact_id, name=f"{nome} — {veh}"
            )
            opp_id = resp.get("id") or (resp.get("opportunity") or {}).get("id")
            created = bool(opp_id)
        if not opp_id:
            logger.warning("runtime.opportunity_no_id contact_id={}", contact_id)
            return
        state["opportunity_id"] = opp_id
        try:
            await get_agent().aupdate_session_state(
                {"opportunity_id": opp_id}, session_id=contact_id
            )
        except Exception as e:
            logger.warning("runtime.opportunity_persist_failed err={}", e)
        # Vocabulário canônico: CREATED na criação, UPDATED no reuso.
        event_type = "OPPORTUNITY_CREATED" if created else "OPPORTUNITY_UPDATED"
        payload = {
            "opportunity_id": opp_id,
            "pipeline_id": settings.ghl_pipeline_id,
            "stage_id": settings.ghl_pipeline_stage_id or None,
            "motivo": motivo,
        }
        if not created:
            payload["status"] = "open"
        await emit_event(
            event_type,
            contact_id=contact_id,
            conversation_id=conversation_id,
            session_id=contact_id,
            payload=payload,
        )
        logger.info(
            "runtime.opportunity_linked contact_id={} opp_id={} event={}",
            contact_id, opp_id, event_type,
        )
    except Exception as e:
        logger.exception("runtime.opportunity_link_failed contact_id={} err={}", contact_id, e)


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
        turn_input, _ = await concat.build_turn_input(
            pending, contact_id=contact_id, conversation_id=conversation_id
        )
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
        current_state["conversation_id"] = conversation_id  # persiste p/ join CRM↔sessão
        reopened = _maybe_reopen(current_state, messages)
        _seed_ad_meta(current_state, ad_meta or {})

        # CONVERSATION_STARTED: primeira vez que processamos este contato
        # (sem sessão prévia) ou após reabertura de uma conversa encerrada.
        tel = current_state.setdefault("telemetry", {})
        if (prev_state is None or reopened) and not tel.get("started_emitted"):
            tel["started_emitted"] = True
            await emit_event(
                "CONVERSATION_STARTED",
                contact_id=contact_id,
                conversation_id=conversation_id,
                session_id=contact_id,
                payload={"reopened": reopened, "ad_meta": current_state.get("ad_meta") or {}},
            )

        if (current_state.get("handoff") or {}).get("feito") and not reopened:
            logger.info("runtime.terminal contact_id={}", contact_id)
            metrics.TURNS.labels(result="terminal").inc()
            return

        # Ancora a última mensagem do lead no state pra o guard anti-alucinação
        # de registrar_lead_info validar valores contra o que foi realmente dito.
        current_state["_last_user_msg"] = turn_input

        # Coleta de funil completa → qualificado. Dedup: emite o evento/metrica
        # UMA vez por conversa (antes incrementava todo turno → inflava).
        if not missing_fields(current_state) and not tel.get("qualified_emitted"):
            tel["qualified_emitted"] = True
            metrics.QUALIFICADOS.inc()
            await emit_event(
                "LEAD_QUALIFIED",
                contact_id=contact_id,
                conversation_id=conversation_id,
                session_id=contact_id,
                payload={"intencao": current_state.get("intencao")},
            )

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
        _elapsed = time.perf_counter() - _t0
        metrics.LLM_LATENCY.observe(_elapsed)
        await _record_llm_cost(
            result,
            contact_id=contact_id,
            conversation_id=conversation_id,
            session_id=contact_id,
            latency_ms=int(_elapsed * 1000),
        )

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
        # Agendamento: se o lead deu dia/hora e confirmou, reserva no
        # calendário GHL específico e persiste o appointment_id.
        await _maybe_book_appointment(agent, contact_id, post_state)

        handoff = (post_state.get("handoff") or {})
        if handoff.get("feito"):
            motivo = handoff.get("motivo") or "coleta_completa"
            ag = post_state.get("agendamento") or {}
            # Guard: handoff de agendamento confirmado SÓ é válido se há
            # data_hora de fato. Senão o modelo encerrou cedo demais — reverte
            # e mantém a sessão ativa pra coletar o dia/horário.
            if motivo == "agendamento_confirmado" and not ag.get("data_hora"):
                logger.warning(
                    "runtime.handoff_reverted contact_id={} motivo=agendamento_confirmado sem data_hora",
                    contact_id,
                )
                post_state.setdefault("handoff", {})["feito"] = False
                post_state["handoff"]["motivo"] = None
                try:
                    await agent.aupdate_session_state(
                        {"handoff": {"feito": False, "motivo": None}}, session_id=contact_id
                    )
                except Exception as e:
                    logger.warning("runtime.handoff_revert_persist_failed err={}", e)
            else:
                metrics.HANDOFF.labels(motivo=motivo).inc()
                try:
                    legacy = _legacy_state_for_handoff(post_state)
                    await execute_handoff(contact_id, legacy, motivo)
                except Exception as e:
                    logger.exception("runtime.handoff_exec_failed err={}", e)
                # Eventos: handoff + encerramento da conversa (dedup completed).
                conv_id = post_state.get("conversation_id") or conversation_id
                await emit_event(
                    "HANDOFF_CREATED",
                    contact_id=contact_id,
                    conversation_id=conv_id,
                    session_id=contact_id,
                    payload={"motivo": motivo},
                )
                post_tel = post_state.setdefault("telemetry", {})
                if not post_tel.get("completed_emitted"):
                    post_tel["completed_emitted"] = True
                    await emit_event(
                        "CONVERSATION_COMPLETED",
                        contact_id=contact_id,
                        conversation_id=conv_id,
                        session_id=contact_id,
                        payload={"motivo": motivo, "reopen_count": (post_state.get("counters") or {}).get("reopen", 0)},
                    )
                # Fase 3: vincula/atualiza a oportunidade no CRM (best-effort).
                await _link_opportunity(contact_id, conv_id, post_state, motivo)
                try:
                    await agent.aupdate_session_state(
                        {"telemetry": post_tel}, session_id=contact_id
                    )
                except Exception as e:
                    logger.warning("runtime.telemetry_persist_failed err={}", e)

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
