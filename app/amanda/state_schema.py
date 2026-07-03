"""Shape do session_state que o Agno persiste no Postgres como JSONB.

É um dict puro (não Pydantic) porque o Agno serializa session_state via
json.dumps. Os helpers abaixo apenas garantem chaves padrão.
"""
from __future__ import annotations

from typing import Any


def default_state() -> dict[str, Any]:
    return {
        "lead": {"nome": None, "cidade": None, "regiao": None},
        "intencao": None,
        "veiculo_interesse": None,
        "troca": {
            "modelo": None,
            "ano": None,
            "km": None,
            "quitado_ou_financiado": None,
            "fotos_solicitadas": None,
            "forma_pagamento_diferenca": None,
        },
        "financiamento": {
            "cpf": None,
            "data_nascimento": None,
            "entrada": None,
            "parcela_desejada": None,
            "cnh": None,
        },
        "vista_confirmado": None,
        "carta_credito_contemplada": None,
        "pendencias": [],
        "agendamento": {
            "oferecido": False,
            "confirmado": False,
            "tipo": None,
            "data_hora": None,
            "appointment_id": None,
        },
        "ad_meta": {},
        "handoff": {"feito": False, "motivo": None},
        "stage": "abertura",
        "conversation_id": None,
        "opportunity_id": None,
        # Flags de telemetria (eventos emitidos uma única vez por conversa).
        "telemetry": {
            "started_emitted": False,
            "qualified_emitted": False,
            "completed_emitted": False,
        },
        "greeted": False,
        "counters": {
            "ai_identity_asked": 0,
            "humano_solicitado": 0,
            "reopen": 0,
            "deflexao": 0,
        },
        "last_asked": [],
    }


def ensure_keys(state: dict[str, Any] | None) -> dict[str, Any]:
    """Mescla state existente com defaults — não regride dados."""
    base = default_state()
    if not state:
        return base
    for k, v in base.items():
        if k not in state:
            state[k] = v
        elif isinstance(v, dict) and isinstance(state.get(k), dict):
            for sk, sv in v.items():
                if sk not in state[k]:
                    state[k][sk] = sv
    return state


# Campos base sempre obrigatórios
BASE_FIELDS = ("lead.nome", "lead.cidade", "intencao")

TROCA_FIELDS = (
    "troca.modelo",
    "troca.ano",
    "troca.km",
    "troca.quitado_ou_financiado",
    "troca.fotos_solicitadas",
    "troca.forma_pagamento_diferenca",
)

# Ordem: qualificação leve PRIMEIRO (entrada/parcela/CNH), dado sensível
# (CPF/nascimento) por ÚLTIMO — só na hora de fechar a simulação. Pedir CPF
# logo de cara assusta o lead (reação "isso é golpe").
FINANCIAMENTO_FIELDS = (
    "financiamento.entrada",
    "financiamento.parcela_desejada",
    "financiamento.cnh",
    "financiamento.cpf",
    "financiamento.data_nascimento",
)

VISTA_FIELDS = ("vista_confirmado",)
CARTA_FIELDS = ("carta_credito_contemplada",)


def get_dotted(state: dict[str, Any], dotted: str) -> Any:
    cur: Any = state
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def set_dotted(state: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = state
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def funnel_for(state: dict[str, Any]) -> tuple[str, ...]:
    # Forma de pagamento EXPLÍCITA do lead vence a intenção previamente inferida.
    # Ex.: lead disse "primeiro carro" e depois "vou fazer à vista" → não exigir
    # CPF/entrada/parcela (funil de financiamento) — a pivô do lead manda.
    if state.get("vista_confirmado") is True:
        return BASE_FIELDS + VISTA_FIELDS
    if state.get("carta_credito_contemplada") is True:
        return BASE_FIELDS + CARTA_FIELDS

    intent = state.get("intencao")
    if intent == "troca":
        base = BASE_FIELDS + TROCA_FIELDS
        # Só ramifica pro funil de financiamento se o lead disser que financia a
        # DIFERENÇA. "apenas_troca" (o carro de troca cobre tudo / é a única
        # entrada) e "vista" NÃO pedem CPF/entrada/parcela — não re-perguntar.
        if (state.get("troca") or {}).get("forma_pagamento_diferenca") == "financiamento":
            base = base + FINANCIAMENTO_FIELDS
        return base
    if intent == "vista":
        return BASE_FIELDS + VISTA_FIELDS
    if intent == "carta_credito":
        return BASE_FIELDS + CARTA_FIELDS
    if intent in ("financiamento", "primeiro_carro"):
        return BASE_FIELDS + FINANCIAMENTO_FIELDS
    return BASE_FIELDS


def missing_fields(state: dict[str, Any]) -> list[str]:
    return [f for f in funnel_for(state) if not _is_filled(state, f)]


def _is_filled(state: dict[str, Any], dotted: str) -> bool:
    v = get_dotted(state, dotted)
    return not (v is None or v == "")
