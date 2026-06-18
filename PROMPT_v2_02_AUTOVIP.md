Você é o agente de engenharia do repositório `zaf-autovip` (Amanda, Auto Vip).

CONTEXTO
Adequação (Fases 1-3) já APLICADA na branch `feat/telemetria-hub-fase1`. Validação central achou desvios do CONTRATO CANÔNICO v1. Rodada de CORREÇÃO (v2). Referência: `/Users/raulbehnke/var-zoi/CONTRATO_EVENTOS_CANONICO.md`. Atualize código + `RELATORIO_APLICACAO_TELEMETRIA_AUTOVIP.md`.

O QUE JÁ ESTÁ CERTO (não regredir)
- `llm_calls` + `agent_events` + `pricing`, custo por conversa, Whisper (verbose_json), logs JSON, dedup de qualificados, `pricing_version`, Opportunities best-effort, telemetria best-effort. Manter.

GAPS A CORRIGIR (bloqueiam integração)

1. ENVELOPE CANÔNICO incompleto. `agent_events` (e `llm_calls` no que exportar ao Hub) NÃO têm `event_id`, `schema_version`, `client`. Adicionar:
   - `event_id` TEXT UNIQUE NOT NULL = `uuid4()` (idempotência — Hub deduplica por isso).
   - `schema_version` INTEGER DEFAULT 1.
   - `client` TEXT = `"autovip"` (manter `agent="amanda-autovip"`).
   Preencher em `app/telemetry/events.py`.

2. CUSTO EM BRL. Hoje só `cost_usd`. Adicionar BRL:
   - `pricing` ganha `usd_brl_rate`.
   - `app/pricing.py`: `cost_chat`/`cost_whisper` retornam `(cost_usd, cost_brl, pricing_version)`.
   - `llm_calls` e payload de eventos ganham `cost_brl` + `usd_brl_rate` (já têm `pricing_version`).

3. VOCABULÁRIO de evento. Renomear `OPPORTUNITY_LINKED` → `OPPORTUNITY_CREATED` (na criação) e `OPPORTUNITY_UPDATED` (na atualização/reuso). Ajustar `runtime._link_opportunity`.

ENTREGÁVEL
- Código + validação isolada (mesmo padrão atual: py_compile + import + cálculo de custo). Confirmar `cost_brl` correto (ex.: chat 1000/500 tok × câmbio).
- Atualizar relatório: seção "Correções v2", envelope canônico, eventos renomeados, exemplo de `LLM_CALL`.
- Manter `request_id` best-effort.

REGRA: cite arquivos reais (app/telemetry/*, app/pricing.py, app/amanda/runtime.py, app/ghl/opportunities.py). Nada genérico.
