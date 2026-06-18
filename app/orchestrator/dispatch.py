"""Tool dispatch determinístico chamado pelo orchestrator.

Substitui as @tool do Agno. Funções simples Python que o orchestrator decide
chamar baseado em update.intent / intent_secundario.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import pytz
from loguru import logger

from app.agent.state import SessionState, StateUpdate
from app.config import settings
from app.ghl import contacts, custom_values

_TZ = pytz.timezone("America/Sao_Paulo")


def business_hours_status() -> Literal["open", "closed"]:
    now = datetime.now(_TZ)
    weekday = now.weekday()
    hour = now.hour
    if weekday <= 4:  # Mon-Fri
        return "open" if 9 <= hour < 18 else "closed"
    if weekday == 5:  # Sat
        return "open" if 9 <= hour < 12 else "closed"
    return "closed"


async def fetch_faq() -> str:
    try:
        return await custom_values.get_custom_value(settings.faq_custom_value_id)
    except Exception as e:
        logger.error("dispatch.fetch_faq failed err={}", e)
        return ""


async def dispatch(
    *,
    state: SessionState,
    update: StateUpdate,
    last_message: str = "",
) -> dict[str, Any]:
    """Decide quais recursos buscar antes do responder.

    FAQ é buscado quando o UPDATER (LLM) julgou que o turno tem uma pergunta
    do lead que merece resposta — i.e., classificou como dúvida explícita,
    dúvida operacional, pedido de foto, ou registrou pendências novas.
    Sem heurística mecânica de "?": confiamos no juízo do classifier.
    """
    out: dict[str, Any] = {}

    needs_faq = (
        update.intent == "duvida"
        or update.intent_secundario in ("duvida_operacional", "pedido_foto")
        or bool(update.pendencias_novas)
    )
    if needs_faq:
        out["faq_yaml"] = await fetch_faq()

    return out


def format_handoff_summary(state: SessionState, reason: str) -> str:
    c = state.collected
    lines = [
        "Resumo do atendimento IA — Auto Vip",
        "",
        f"Motivo do handoff: {reason}",
        "",
        f"Nome: {c.nome or '-'}",
        f"Cidade: {c.cidade or '-'}",
        f"Veículo de interesse: {c.veiculo_interesse or '-'}",
        f"Intenção: {c.intencao or '-'}",
    ]
    t = c.troca
    has_troca = bool(t) and (
        c.intencao == "troca"
        or any([t.modelo, t.ano, t.km, t.quitado_ou_financiado,
                t.forma_pagamento_diferenca, t.fotos_solicitadas])
    )
    if has_troca:
        lines += [
            "",
            "Carro de troca:",
            f"  Modelo: {t.modelo or '-'}",
            f"  Ano: {t.ano or '-'}",
            f"  KM: {t.km or '-'}",
            f"  Status: {t.quitado_ou_financiado or '-'}",
            f"  Fotos: {'sim' if t.fotos_solicitadas else 'pendente'}",
            f"  Pagamento da diferença: {t.forma_pagamento_diferenca or '-'}",
        ]
    f = c.financiamento
    has_fin = bool(f) and any(
        [f.cpf, f.data_nascimento, f.entrada, f.parcela_desejada, f.cnh]
    )
    if has_fin:
        lines += [
            "",
            "Financiamento:",
            f"  CPF: {f.cpf or '-'}",
            f"  Data nascimento: {f.data_nascimento or '-'}",
            f"  Entrada: {f.entrada or '-'}",
            f"  Parcela desejada: {f.parcela_desejada or '-'}",
            f"  CNH: {'sim' if f.cnh else '-'}",
        ]
    if c.vista_confirmado is not None:
        lines += ["", f"À vista confirmado: {c.vista_confirmado}"]
    if c.carta_credito_contemplada is not None:
        lines += ["", f"Carta de crédito contemplada: {c.carta_credito_contemplada}"]
    if state.agendamento and state.agendamento.data_hora:
        lines += [
            "",
            f"Agendamento: {state.agendamento.tipo} em {state.agendamento.data_hora}",
        ]
    if state.pendencias:
        lines += ["", "Pendências pro consultor:"]
        for p in state.pendencias:
            lines.append(f"  - {p}")
    return "\n".join(lines)


# IDs dos custom fields do GHL (location Auto Vip). Atualizados no handoff.
_CF = {
    "cpf": "qWbrAW2Kvc0p1y8KfSoT",            # CPF / CNPJ
    "data_nascimento": "Rm6M9cOmWamf0gfbIG8R",  # Data de Nascimento
    "veiculo_interesse": "YBhcJXRfaB909Cr0NosJ",  # VEÍCULO DE INTERESSE
    "entrada": "0gfETKm8KHFX296Ia2b6",          # Valor Entrada
    "veiculo_troca": "7atOLADN32PVvIrshkZh",    # Veículo de Troca
    "troca_modelo": "OYZitbjkLmbUixsVt9y3",     # Modelo do Veículo
    "troca_ano": "KRu9incMGBQ78Mjdesb0",        # Ano do Veículo
    "troca_km": "ytsZpl73lGnyThrkS46r",         # KM do Veículo
}


def build_custom_fields(state: SessionState) -> list[dict]:
    """Monta a lista de custom fields {id, value} a partir do que foi coletado.
    Só inclui campos com valor (não apaga o que está vazio)."""
    c = state.collected
    out: list[dict] = []

    def put(fid: str, value) -> None:
        if value not in (None, "", []):
            out.append({"id": fid, "value": str(value)})

    put(_CF["veiculo_interesse"], c.veiculo_interesse)
    f = c.financiamento
    if f:
        put(_CF["cpf"], f.cpf)
        put(_CF["data_nascimento"], f.data_nascimento)
        put(_CF["entrada"], f.entrada)
    t = c.troca
    if t and (c.intencao == "troca" or any([t.modelo, t.ano, t.km])):
        put(_CF["veiculo_troca"], t.modelo)
        put(_CF["troca_modelo"], t.modelo)
        put(_CF["troca_ano"], t.ano)
        put(_CF["troca_km"], t.km)
    return out


async def execute_handoff(contact_id: str, state: SessionState, reason: str) -> None:
    summary = format_handoff_summary(state, reason)
    try:
        await contacts.add_note(contact_id, summary)
    except Exception as e:
        logger.exception("handoff add_note failed err={}", e)
    try:
        await contacts.add_handoff_note(
            contact_id, summary, settings.ramon_user_id, mentioned_name="Ramon",
        )
    except Exception as e:
        logger.exception("handoff add_handoff_note failed err={}", e)
    try:
        fields = build_custom_fields(state)
        if fields:
            await contacts.update_custom_fields(contact_id, fields)
            logger.info("handoff.custom_fields_updated contact_id={} n={}", contact_id, len(fields))
    except Exception as e:
        logger.exception("handoff update_custom_fields failed err={}", e)
    try:
        # Remove AS DUAS grafias da tag de gate — senão o bot continua ativo.
        await contacts.remove_tag(contact_id, ["agente-ia", "agent-ia"])
    except Exception as e:
        logger.exception("handoff remove_tag failed err={}", e)
    logger.info("handoff.done contact_id={} reason={}", contact_id, reason)
