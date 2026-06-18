"""Métricas Prometheus da Amanda.

Exposição em GET /metrics (ver app.main). Contadores e histogramas são
processo-globais (default registry). Instrumentação fica nos pontos quentes:
runtime (turnos/handoff/latência LLM), hooks (tools/violações de bolha),
ghl.client (latência/erros de API).
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Turnos por resultado: run | no_pending | no_conversation | empty_input |
# empty_reply | terminal | error
TURNS = Counter(
    "amanda_turns_total", "Turnos processados por resultado", ["result"]
)

# Handoffs disparados, por motivo.
HANDOFF = Counter(
    "amanda_handoff_total", "Handoffs para consultor humano", ["motivo"]
)

# Coletas completas (funil sem faltantes no início do turno).
QUALIFICADOS = Counter(
    "amanda_qualificados_total", "Turnos com coleta de funil completa"
)

# Violações das regras de bolha detectadas pelo post-hook.
# kind: too_many | question_not_last | string_fallback | recovered
BUBBLE_VIOLATIONS = Counter(
    "amanda_bubble_violations_total", "Violações de regra de bolha", ["kind"]
)

# Chamadas de tool por nome.
TOOL_CALLS = Counter("amanda_tool_calls_total", "Chamadas de tool", ["name"])

# Rejeições do guard anti-alucinação em registrar_lead_info.
ALUC_REJECTS = Counter(
    "amanda_aluc_rejects_total", "Valores rejeitados pelo guard anti-alucinação"
)

# Latência do agent.arun (segundos).
LLM_LATENCY = Histogram(
    "amanda_llm_latency_seconds", "Latência do agent.arun (s)"
)

# Consumo de tokens por turno (input/output) e custo estimado em USD.
LLM_TOKENS = Counter("amanda_llm_tokens_total", "Tokens LLM consumidos", ["kind"])
LLM_COST_USD = Counter("amanda_llm_cost_usd_total", "Custo LLM estimado (USD)")

# Falhas por quota/billing da OpenAI (429 insufficient_quota).
OPENAI_QUOTA_ERRORS = Counter(
    "amanda_openai_quota_errors_total", "Turnos falhos por quota OpenAI esgotada"
)

# Latência e erros das chamadas GHL.
GHL_LATENCY = Histogram(
    "amanda_ghl_latency_seconds", "Latência de chamadas GHL (s)", ["path"]
)
GHL_ERRORS = Counter(
    "amanda_ghl_errors_total", "Respostas GHL não-2xx", ["status"]
)


def render() -> tuple[bytes, str]:
    """Retorna (payload, content_type) para a rota /metrics."""
    return generate_latest(), CONTENT_TYPE_LATEST
