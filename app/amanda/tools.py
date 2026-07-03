"""Tools que a Amanda Agent pode invocar.

Cada tool tem docstring rica — o Agno usa pra montar o JSON schema que o
modelo vê. Convenção: tools que mutam estado recebem ``run_context`` e
escrevem em ``run_context.session_state``.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz
import yaml
from agno.run.base import RunContext
from agno.tools import tool
from loguru import logger

from app import metrics
from app.amanda import region
from app.amanda.state_schema import (
    ensure_keys,
    get_dotted,
    missing_fields,
    set_dotted,
)
from app.config import settings
from app.ghl import custom_values

_TZ = pytz.timezone("America/Sao_Paulo")
_FAQ_PATH = Path(__file__).resolve().parents[2] / "data" / "faq.yaml"
_FAQ_CACHE: dict[str, str] | None = None


def _load_local_faq() -> dict[str, str]:
    try:
        with _FAQ_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {k: str(v).strip() for k, v in data.items()}
    except Exception as e:
        logger.error("faq.load_local failed err={}", e)
        return {}


def _load_faq() -> dict[str, str]:
    """FAQ corrente (cache). Default = arquivo local; pode ser sobrescrito
    pela fonte canônica do GHL via `refresh_faq_from_ghl` no startup."""
    global _FAQ_CACHE
    if _FAQ_CACHE is None:
        _FAQ_CACHE = _load_local_faq()
    return _FAQ_CACHE


async def refresh_faq_from_ghl() -> None:
    """Carrega o FAQ da fonte canônica (GHL Custom Value YAML) e sobrepõe o
    cache. Mantém o local como fallback se o GHL falhar ou não estiver
    configurado. Chamado no lifespan do app (e pode ser reagendado)."""
    global _FAQ_CACHE
    base = _load_local_faq()
    if not settings.faq_custom_value_id:
        _FAQ_CACHE = base
        logger.info("faq.ghl_skip (sem faq_custom_value_id) usando local n={}", len(base))
        return
    try:
        raw = await custom_values.get_custom_value(settings.faq_custom_value_id)
        data = yaml.safe_load(raw) or {}
        ghl = {k: str(v).strip() for k, v in data.items()}
        base.update(ghl)  # GHL sobrepõe local
        _FAQ_CACHE = base
        logger.info("faq.ghl_loaded n_ghl={} n_total={}", len(ghl), len(base))
    except Exception as e:
        _FAQ_CACHE = base
        logger.warning("faq.ghl_failed fallback_local n={} err={}", len(base), e)


# ---------------------------------------------------------------------------
# State mutation tools
# ---------------------------------------------------------------------------

_VALID_FIELDS = {
    "lead.nome",
    "lead.cidade",
    "intencao",
    "veiculo_interesse",
    "troca.modelo",
    "troca.ano",
    "troca.km",
    "troca.quitado_ou_financiado",
    "troca.fotos_solicitadas",
    "troca.forma_pagamento_diferenca",
    "financiamento.cpf",
    "financiamento.data_nascimento",
    "financiamento.entrada",
    "financiamento.parcela_desejada",
    "financiamento.cnh",
    "vista_confirmado",
    "carta_credito_contemplada",
}

# Campos de texto livre / numéricos cujo valor o lead PRECISA ter dito
# literalmente — guardamos contra alucinação (modelo inventar nome/modelo/cpf).
# Campos booleanos/enumerados (intencao, *_ou_financiado, fotos_solicitadas,
# forma_pagamento_diferenca, vista_confirmado, carta, cnh) são inferíveis de
# linguagem curta e ficam FORA do guard.
_GUARDED_TEXT_FIELDS = {
    "lead.nome",
    "lead.cidade",
    "veiculo_interesse",
    "troca.modelo",
}
_GUARDED_NUMERIC_FIELDS = {
    "troca.ano",
    "troca.km",
    "financiamento.entrada",
    "financiamento.parcela_desejada",
    "financiamento.data_nascimento",
    "financiamento.cpf",
}


def _norm(s: str) -> str:
    """lowercase + sem acento + espaços colapsados."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def _expand_multipliers(msg: str) -> str:
    """Expande multiplicadores por extenso pra o match numérico funcionar:
    "210mil" / "210 mil" → "210000"; "50k" → "50000"; "2 milhões" → "2000000".
    """
    s = _norm(msg)
    s = re.sub(r"(\d+)\s*mil(?:h(?:ao|oes))", lambda m: m.group(1) + "000000", s)  # milhão/milhões
    s = re.sub(r"(\d+)\s*mil\b", lambda m: m.group(1) + "000", s)
    s = re.sub(r"(\d+)\s*k\b", lambda m: m.group(1) + "000", s)
    return s


def _normalize_money(raw_value: Any, last_msg: str = "") -> str:
    """Normaliza valor de dinheiro entendendo "mil"/"k": "7 mil"→"7000",
    "2k"→"2000". Pega o multiplicador do próprio valor OU da mensagem (quando
    o modelo extraiu só "7" de "7 mil")."""
    s = _norm(raw_value)
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return str(raw_value)
    # multiplicador no próprio valor ("7 mil", "2k", "3 milhões")
    if re.search(r"\d\s*mil(h(ao|oes))?\b", s):
        mult = 1_000_000 if re.search(r"\d\s*milh", s) else 1000
        return str(int(digits) * mult)
    if re.search(r"\d\s*k\b", s):
        return str(int(digits) * 1000)
    # multiplicador na MENSAGEM associado a esse número ("uns 7 mil")
    if last_msg:
        nmsg = _norm(last_msg)
        if re.search(rf"\b{digits}\s*milh", nmsg):
            return str(int(digits) * 1_000_000)
        if re.search(rf"\b{digits}\s*(mil|k)\b", nmsg):
            return str(int(digits) * 1000)
    return digits


def _value_supported_by_msg(campo: str, valor: Any, last_msg: str) -> bool:
    """Anti-alucinação: o valor precisa estar ancorado na mensagem do lead.

    - Texto livre: todas as palavras alfanuméricas do valor aparecem na msg
      (substring normalizada OU todos os tokens presentes).
    - Numérico: os dígitos do valor aparecem nos dígitos da msg (após expandir
      multiplicadores por extenso como "mil"/"k"). Também aceita o caso em que
      os dígitos da msg são prefixo do valor (ex.: lead diz "210", modelo grava
      210000).
    - Sem `last_msg` (ex.: teste direto) → não bloqueia (retorna True).
    """
    if not last_msg:
        return True
    nmsg = _norm(last_msg)
    if campo in _GUARDED_NUMERIC_FIELDS:
        digits = "".join(c for c in str(valor) if c.isdigit())
        if not digits:
            return True
        expanded = _expand_multipliers(last_msg)
        msg_digits = "".join(c for c in expanded if c.isdigit())
        if digits in msg_digits:
            return True
        # fallback: lead disse a forma curta ("210") e modelo expandiu (210000)
        stripped = digits.rstrip("0")
        return bool(stripped) and stripped in msg_digits
    if campo in _GUARDED_TEXT_FIELDS:
        nval = _norm(valor)
        if not nval:
            return True
        if nval in nmsg:
            return True
        tokens = [t for t in re.split(r"\W+", nval) if t]
        msg_tokens = set(re.split(r"\W+", nmsg))
        return bool(tokens) and all(t in msg_tokens for t in tokens)
    return True


# Sinais que ANCORAM cada intenção na mensagem do lead. Sem um desses, o
# modelo NÃO pode registrar a intenção (anti-presunção). O auto-derive
# (derive_intent) é a exceção — só dispara em campos de troca já ancorados.
_INTENT_SIGNALS = {
    "troca": (
        "troc", "na troca", "meu carro", "carro atual", "o meu", "dou meu",
        "dar meu", "de entrada o", "tenho um", "tenho uma", "meu gol",
        "trocar",
    ),
    "financiamento": (
        "financ", "a prazo", "parcelar", "parcelad", "no banco", "credito",
        "crédito",
    ),
    "vista": (
        "a vista", "à vista", "avista", "dinheiro", "pago tudo", "pagar tudo",
        "a vista mesmo", "tudo de uma vez",
    ),
    "carta_credito": (
        "carta de credito", "carta de crédito", "carta contemplada",
        "consorcio", "consórcio", "contemplad",
    ),
    "primeiro_carro": (
        "primeiro carro", "primeira vez", "nunca tive", "meu primeiro",
        "primeiro veiculo", "primeiro veículo",
    ),
}


def _intent_supported_by_msg(valor: Any, last_msg: str) -> bool:
    """True se a intenção declarada tem sinal na mensagem do lead. Sem
    `last_msg` (teste direto) não bloqueia."""
    if not last_msg:
        return True
    sigs = _INTENT_SIGNALS.get(str(valor))
    if not sigs:
        return True  # valor desconhecido → não bloqueia aqui
    n = _norm(last_msg)
    return any(s in n for s in sigs)


_DEFLEXOES = (
    "essa parte quem confirma certinho é o consultor",
    "deixa eu adiantar essa pro consultor te responder",
    "essa o consultor te detalha melhor que eu",
    "essa eu já passo pro consultor ver pra você",
    "isso o consultor consegue te confirmar direitinho",
)


@tool
def registrar_lead_info(
    run_context: RunContext, campo: str, valor: str | bool | int | float
) -> dict[str, Any]:
    """Grava uma informação que o lead acabou de fornecer.

    Use SEMPRE que o lead informar algo novo (nome, cidade, modelo do carro,
    ano, quilometragem, CPF, valor de entrada, parcela desejada, status do
    carro, intenção de compra etc.). Chame ANTES de gerar a próxima pergunta.

    Args:
        campo: caminho dotted do campo. Valores válidos:
            "lead.nome", "lead.cidade",
            "intencao" (troca|financiamento|vista|carta_credito|primeiro_carro),
            "veiculo_interesse",
            "troca.modelo", "troca.ano", "troca.km",
            "troca.quitado_ou_financiado" (quitado|financiado),
            "troca.fotos_solicitadas" (true|false),
            "troca.forma_pagamento_diferenca" (vista|financiamento|apenas_troca),
            "financiamento.cpf", "financiamento.data_nascimento",
            "financiamento.entrada", "financiamento.parcela_desejada",
            "financiamento.cnh" (true|false),
            "vista_confirmado" (true|false),
            "carta_credito_contemplada" (true|false).
        valor: texto cru do que o lead disse, normalizado. Para campos
            booleanos use "true"/"false". Para números (ano, km) use só dígitos.

    Returns:
        dict com {ok, faltantes}: lista dos campos do funil ainda vazios.
    """
    state = ensure_keys(run_context.session_state or {})
    run_context.session_state = state

    if campo not in _VALID_FIELDS:
        return {"ok": False, "erro": f"campo invalido: {campo}"}

    parsed: Any = valor
    if isinstance(valor, bool):
        parsed = valor
    elif isinstance(valor, (int, float)) and campo in ("troca.ano", "troca.km"):
        parsed = int(valor)
    elif isinstance(valor, str):
        v = valor.strip()
        if v.lower() in ("true", "sim", "yes"):
            parsed = True
        elif v.lower() in ("false", "nao", "não", "no"):
            parsed = False
        elif campo == "troca.ano":
            digits = "".join(c for c in v if c.isdigit())
            parsed = int(digits) if digits else None
        elif campo == "troca.km":
            norm = _normalize_money(v, str(state.get("_last_user_msg") or ""))
            parsed = int(norm) if norm.isdigit() else None
        elif campo in ("financiamento.entrada", "financiamento.parcela_desejada"):
            # entende "7 mil"→7000, "2k"→2000 (do valor ou da mensagem).
            parsed = _normalize_money(v, str(state.get("_last_user_msg") or ""))
        else:
            parsed = v

    # Guard anti-alucinação: valor de texto/numérico precisa estar ancorado
    # na última mensagem do lead (injetada pelo runtime em _last_user_msg).
    last_msg = str(state.get("_last_user_msg") or "")
    if not _value_supported_by_msg(campo, parsed, last_msg):
        logger.warning(
            "tool.registrar_lead_info.rejected campo={} valor={!r} (nao ancorado na msg)",
            campo, parsed,
        )
        metrics.ALUC_REJECTS.inc()
        return {
            "ok": False,
            "erro": "valor nao encontrado na mensagem do lead; nao invente dados",
            "faltantes": missing_fields(state),
        }

    # Guard de INTENÇÃO: o modelo não pode presumir intenção sem sinal do
    # lead na mensagem (ex.: lead só perguntou "tem a T-Cross?" → NÃO é troca).
    if campo == "intencao" and not _intent_supported_by_msg(parsed, last_msg):
        logger.warning(
            "tool.registrar_lead_info.intent_rejected valor={!r} (sem sinal na msg)", parsed
        )
        metrics.ALUC_REJECTS.inc()
        return {
            "ok": False,
            "erro": "o lead nao sinalizou essa intencao; nao presuma. PERGUNTE "
                    "a intencao de forma neutra (primeiro carro, troca, financiar ou a vista).",
            "faltantes": missing_fields(state),
        }

    # Pivô de pagamento: lead que disse 'primeiro carro'/'financiamento' e depois
    # confirma à vista/carta pode SOBRESCREVER a intenção fraca anterior.
    _weak_intents = {"primeiro_carro", "financiamento"}
    if (
        campo == "intencao"
        and parsed in ("vista", "carta_credito")
        and get_dotted(state, campo) in _weak_intents
    ):
        set_dotted(state, campo, parsed)
    elif get_dotted(state, campo) in (None, "") and parsed not in (None, ""):
        set_dotted(state, campo, parsed)

    if campo == "lead.cidade":
        reg = region.classify(str(valor))
        if reg:
            state["lead"]["regiao"] = reg

    derived = derive_intent(state, campo, parsed)
    if derived:
        logger.info("tool.registrar_lead_info.intent_derived intencao={} de campo={}",
                    derived, campo)

    logger.info("tool.registrar_lead_info campo={} valor={}", campo, parsed)
    return {"ok": True, "faltantes": missing_fields(state)}


def derive_intent(state: dict[str, Any], campo: str, parsed: Any) -> str | None:
    """Auto-deriva `intencao` de dados inequívocos, pra o funil não re-perguntar
    'primeiro carro ou troca?' depois que o lead já descreveu o carro da troca /
    confirmou à vista / carta. MUTA state. Retorna a intenção derivada ou None.

    Confirmação EXPLÍCITA de forma de pagamento (à vista / carta contemplada)
    SOBREPÕE uma intenção fraca anterior (primeiro_carro / financiamento) — o
    lead pode dizer 'primeiro carro' e depois pivotar pra 'à vista'."""
    cur = state.get("intencao")
    # Pivô forte: à vista / carta vencem intenção fraca já registrada.
    if campo == "vista_confirmado" and parsed is True and cur != "vista":
        if cur in (None, "", "primeiro_carro", "financiamento"):
            state["intencao"] = "vista"
            return "vista"
        return None
    if campo == "carta_credito_contemplada" and parsed is True and cur != "carta_credito":
        if cur in (None, "", "primeiro_carro", "financiamento"):
            state["intencao"] = "carta_credito"
            return "carta_credito"
        return None

    if cur:
        return None
    intent = None
    # SÓ deriva troca dos campos que descrevem o CARRO da troca — não de
    # forma_pagamento_diferenca/fotos (que o modelo pode setar falando de
    # pagamento e travaria o funil em troca por engano).
    if campo in ("troca.modelo", "troca.ano", "troca.km",
                 "troca.quitado_ou_financiado"):
        intent = "troca"
    if intent:
        state["intencao"] = intent
    return intent


@tool
def consultar_faq(topico: str) -> dict[str, Any]:
    """Busca resposta canônica da loja sobre um tópico operacional.

    Use SEMPRE que o lead fizer uma pergunta sobre como a loja funciona
    (aceita troca, horário, endereço, financiamento, documentos, garantia,
    formas de pagamento etc.). Se a resposta vier, use-a como base pra
    responder ao lead. Se não vier, use marcar_pendencia e dê deflexão suave.

    Args:
        topico: chave do FAQ. Tópicos disponíveis:
            "pega_troca" — aceita carro na troca?
            "horario" — horário de atendimento.
            "endereco" — endereço da loja.
            "financiamento_condicoes" — como funciona financiamento.
            "documentos_financiamento" — quais documentos pro financiamento.
            "formas_pagamento" — formas de pagamento aceitas.
            "vende_carta" — se a loja VENDE carta de crédito/consórcio (NÃO
                vende; só aceita carta contemplada como pagamento). Use quando
                o lead perguntar "vocês vendem carta?", "trabalham com
                consórcio?", "emitem carta de crédito?".
            "garantia" — política de garantia.
            "pega_fotos" — SÓ pra orientar o lead a ENVIAR fotos do carro de
                TROCA dele (avaliação). NUNCA use quando o lead pede pra VER
                fotos de um veículo de interesse ("tem foto do Corolla?").
            "precisa_cnh_financiar" — CNH é obrigatória pra financiar.
            "dia_visita" — pode ir presencialmente quando.

    Returns:
        {found: bool, resposta: str|None}. Se found=false, use deflexão.
    """
    faq = _load_faq()
    if topico in faq:
        return {"found": True, "resposta": faq[topico]}
    return {"found": False, "resposta": None}


@tool
def marcar_pendencia(run_context: RunContext, texto: str) -> dict[str, Any]:
    """Anota uma dúvida que só o consultor humano pode responder.

    Use quando o lead perguntar:
    - preço atualizado de um veículo,
    - parcela exata de financiamento,
    - disponibilidade/estoque de um modelo específico,
    - desconto/negociação,
    - valor de avaliação em R$ do carro de troca.

    A Amanda NUNCA responde esses pontos — só deflete e marca aqui.

    Args:
        texto: descrição curta da dúvida. Ex: "preço do Civic 2020",
            "parcela em 48x", "tem ainda o Onix branco".

    Returns:
        {ok: true, total: int}.
    """
    state = ensure_keys(run_context.session_state or {})
    run_context.session_state = state
    txt = (texto or "").strip()
    if not txt:
        return {"ok": False}
    existing = {p.lower() for p in state.get("pendencias", [])}
    if txt.lower() not in existing:
        state["pendencias"].append(txt)
    # Deflexão variada determinística: roda o pool por contador pra evitar
    # muleta repetida ("vou deixar anotado") turno após turno.
    counters = state.setdefault("counters", {})
    idx = int(counters.get("deflexao", 0))
    deflexao = _DEFLEXOES[idx % len(_DEFLEXOES)]
    counters["deflexao"] = idx + 1
    logger.info("tool.marcar_pendencia texto={!r} deflexao_idx={}", txt, idx)
    return {
        "ok": True,
        "total": len(state["pendencias"]),
        "deflexao_sugerida": deflexao,
    }


@tool
def agendar_visita(
    run_context: RunContext,
    tipo: str,
    data_hora: str | None = None,
) -> dict[str, Any]:
    """Registra agendamento de visita/chamada com o consultor.

    Use quando o lead aceitar marcar visita presencial OU chamada de vídeo.

    Args:
        tipo: "presencial" (passar na loja) ou "video" (videochamada).
        data_hora: ISO 8601 fuso America/Sao_Paulo (YYYY-MM-DDTHH:MM) SE o
            lead disser dia e hora concretos. Em ambiguidade, passe None
            (consultor define depois).

    Returns:
        {ok, tipo, data_hora}.
    """
    state = ensure_keys(run_context.session_state or {})
    run_context.session_state = state
    if tipo not in ("presencial", "video"):
        return {"ok": False, "erro": "tipo invalido"}
    state["agendamento"]["tipo"] = tipo
    # SEM dia/hora concretos NÃO confirma — o agendamento só fecha (e só vira
    # handoff "agendamento_confirmado") quando há data_hora. Pergunte o
    # dia/horário antes.
    if not data_hora:
        state["agendamento"]["confirmado"] = False
        logger.info("tool.agendar_visita tipo={} data_hora=None (pendente dia/hora)", tipo)
        return {
            "ok": False,
            "erro": "preciso do DIA e HORÁRIO concretos antes de agendar; "
                    "pergunte ao lead que dia e horário fica melhor.",
        }
    state["agendamento"]["data_hora"] = data_hora
    state["agendamento"]["confirmado"] = True
    logger.info("tool.agendar_visita tipo={} data_hora={}", tipo, data_hora)
    return {"ok": True, "tipo": tipo, "data_hora": data_hora}


@tool
def oferecer_agendamento(run_context: RunContext) -> dict[str, Any]:
    """Marca que a oferta de visita foi feita neste turno.

    Use SEMPRE que você for fazer uma oferta proativa de visita ao lead
    (sem ele ter pedido), pra que nos próximos turnos a oferta não se
    repita. Não chame se o lead já pediu agendamento ativamente.
    """
    state = ensure_keys(run_context.session_state or {})
    run_context.session_state = state
    state["agendamento"]["oferecido"] = True
    return {"ok": True}


@tool
def acionar_handoff(run_context: RunContext, motivo: str) -> dict[str, Any]:
    """Encerra o atendimento da IA e passa pro consultor humano.

    Use quando:
    - lead irritado/xingou → motivo="irritacao".
    - lead pediu falar com humano 2x ou mais → motivo="pedido_humano".
    - coleta completa do funil → motivo="coleta_completa".
    - lead local com coleta completa aceitou visita → motivo="agendamento_confirmado".
    - lead distante com financiamento e coleta completa → motivo="simulacao_solicitada".
    - demanda fora do que Amanda pode tratar → motivo="fora_escopo".
    - lead claramente desistiu → motivo="lead_nao_respondeu".

    Args:
        motivo: um dos valores acima.

    Returns:
        {ok, motivo}.
    """
    state = ensure_keys(run_context.session_state or {})
    run_context.session_state = state
    valid = {
        "irritacao", "pedido_humano", "coleta_completa",
        "agendamento_confirmado", "simulacao_solicitada",
        "fora_escopo", "lead_nao_respondeu",
    }
    if motivo not in valid:
        return {"ok": False, "erro": f"motivo invalido"}
    state["handoff"] = {"feito": True, "motivo": motivo}
    state["stage"] = "fechado"
    logger.info("tool.acionar_handoff motivo={}", motivo)
    return {"ok": True, "motivo": motivo}


@tool
def verificar_horario_loja() -> dict[str, Any]:
    """Retorna se a loja está aberta agora no fuso America/Sao_Paulo.

    Use ao decidir tom de despedida em handoff: se fechado, dizer "amanhã
    o consultor te chama"; se aberto, "o consultor já vai te chamar".

    Returns:
        {status: "open"|"closed", hora_local: str}.
    """
    now = datetime.now(_TZ)
    weekday = now.weekday()
    hour = now.hour
    status = "closed"
    if weekday <= 4 and 9 <= hour < 18:
        status = "open"
    elif weekday == 5 and 9 <= hour < 12:
        status = "open"
    return {"status": status, "hora_local": now.strftime("%Y-%m-%d %H:%M")}


@tool
def consultar_estado(run_context: RunContext) -> dict[str, Any]:
    """Retorna o estado atual da coleta + lista de campos faltantes do funil.

    Use no INÍCIO do turno pra decidir se ainda há campos a coletar ou se
    a coleta está completa.

    Returns:
        {state: dict, faltantes: list[str], proxima_pergunta_sugerida: str|None}.
    """
    state = ensure_keys(run_context.session_state or {})
    run_context.session_state = state
    missing, target, sugestao = pick_next_question(state)
    return {
        "state": state,
        "faltantes": missing,
        "proxima_pergunta_sugerida": sugestao,
        "regiao": state.get("lead", {}).get("regiao"),
    }


def pick_next_question(state: dict[str, Any]) -> tuple[list[str], str | None, str | None]:
    """Lógica pura (testável): escolhe próximo campo do funil com anti-repetição.

    Evita sugerir um campo perguntado nos últimos turnos (rolling window
    `last_asked`). Se todos os faltantes foram perguntados recentemente, cai
    no primeiro faltante mesmo (não trava o funil). Registra o campo escolhido
    na janela (mantém últimas 6). MUTA `state["last_asked"]`.

    Returns: (missing, target_field|None, sugestao_texto|None).
    """
    missing = missing_fields(state)
    if not missing:
        return missing, None, None
    # Anti-repetição estilo AMC: só PULA um campo faltante se ele já foi
    # perguntado >=2x na janela recente (sem resposta útil). Pular na 1ª
    # re-visita é agressivo demais — a mensagem atual do lead normalmente É a
    # resposta ao campo recém-perguntado; pular órfã a resposta (ex.: CPF dado
    # mas nunca gravado, virando loop de re-pergunta).
    recent = list(state.get("last_asked") or [])[-3:]
    target = next((m for m in missing if recent.count(m) < 2), missing[0])
    la = list(state.get("last_asked") or [])
    if not la or la[-1] != target:
        la.append(target)
    state["last_asked"] = la[-6:]
    return missing, target, _suggest_next_question(target)


_SUGESTOES = {
    "lead.nome": "Como posso te chamar?",
    "lead.cidade": "De qual cidade você é?",
    "intencao": "Esse seria seu primeiro carro ou você procura trocar o seu?",
    "troca.modelo": "Qual o modelo do seu atual?",
    "troca.ano": "E o ano dele?",
    "troca.km": "Quilometragem aproximada?",
    "troca.quitado_ou_financiado": "Tá quitado ou ainda financiado?",
    "troca.fotos_solicitadas": "Consegue me mandar umas fotos dele?",
    "troca.forma_pagamento_diferenca": "Como pretende pagar a diferença, à vista ou financiando?",
    "financiamento.cpf": (
        "Certo, Eu vou fazer uma simulação de parcela pra você e conseguir a "
        "melhor proposta. Me passa seu CPF e data de nascimento por gentileza"
    ),
    "financiamento.data_nascimento": "Sua data de nascimento?",
    "financiamento.entrada": "Quanto consegue dar de entrada?",
    "financiamento.parcela_desejada": "Que valor de parcela tá pensando?",
    "financiamento.cnh": "Você já tem CNH?",
    "vista_confirmado": "Confirma então que é compra à vista?",
    "carta_credito_contemplada": "Sua carta de crédito já tá contemplada?",
}


def _suggest_next_question(field: str | None) -> str | None:
    if not field:
        return None
    return _SUGESTOES.get(field)


ALL_TOOLS = [
    registrar_lead_info,
    consultar_faq,
    marcar_pendencia,
    agendar_visita,
    oferecer_agendamento,
    acionar_handoff,
    verificar_horario_loja,
    consultar_estado,
]
