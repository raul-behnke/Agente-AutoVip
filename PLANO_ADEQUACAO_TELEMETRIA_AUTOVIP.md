Siga # PLANO DE ADEQUAÇÃO DE TELEMETRIA — AGENTE "AMANDA" (AUTO VIP) → ZOI PERFORMANCE HUB

> Objetivo: adequar o agente `zaf-autovip` para alimentar o **ZOI Performance Hub** (telemetria operacional / financeira / comercial).
> Escopo: **somente plano**. Nenhuma implementação de código nesta entrega.
> Base: código real do repositório (`app/runtime.py` ≡ `app/amanda/runtime.py`, `app/metrics.py`, `app/amanda/agent.py`, `app/orchestrator/*`, `app/ghl/*`).
> Data: 2026-06-17.

---

## 1. SITUAÇÃO ATUAL

A Amanda **já nasce na frente da frota** em telemetria financeira: ela **captura tokens** e **calcula custo** — algo que a maioria dos agentes não faz. O que falta é **maturidade** (persistência, atribuição, precisão), não fundação.

**O que já existe e funciona:**

| Capacidade | Onde (arquivo real) | Estado |
|---|---|---|
| Captura de tokens por turno | `app/amanda/runtime.py::_record_llm_cost` lê `result.metrics.input_tokens/output_tokens` (RunOutput do Agno) | ✅ funciona, mas só agrega |
| Cálculo de custo | `runtime.py:45` → `custo = (input/1e6)*0.40 + (output/1e6)*1.60` | ✅ roda, preço hardcoded |
| Métricas Prometheus (12) | `app/metrics.py` → `amanda_llm_tokens_total{kind}`, `amanda_llm_cost_usd_total`, `amanda_turns_total{result}`, `amanda_handoff_total{motivo}`, `amanda_qualificados_total`, latências, erros | ✅ exposto em `GET /metrics` (`app/main.py`) |
| Estado de sessão persistido | `app/amanda/agent.py::get_db` → Postgres `amanda_sessions_v2` (JSONB) | ✅ via Agno |
| Lógica de handoff | `app/amanda/tools.py::acionar_handoff` + `app/orchestrator/dispatch.py::execute_handoff` | ✅ |
| Lógica de agendamento | `runtime.py::_maybe_book_appointment` + `app/ghl/calendars.py::book_appointment` | ✅ |
| Lógica de reabertura (24h) | `runtime.py::_maybe_reopen` (`counters.reopen` no JSONB) | ✅ (não é follow-up real) |

**Conclusão:** o trabalho é **transformar telemetria agregada/efêmera em telemetria persistida/atribuível**, e fechar o lado comercial (Opportunities). A base de custo já existe — basta amadurecer.

---

## 2. GAPS

### Operacional
- **O1** — `amanda_turns_total{result="run"}` conta **turnos**, não conversas distintas → contagem de "conversas iniciadas" imprecisa (`runtime.py:273`).
- **O2** — `amanda_qualificados_total` incrementa **por turno** com funil completo → **duplica o mesmo lead** a cada turno (`runtime.py:265-266`).
- **O3** — Follow-up **não existe** como conceito próprio; só há **reopen 24h** (`runtime.py::_maybe_reopen`). Marcar como inexistente.
- **O4** — `conversationId` é obtido em runtime (`conversations.search_conversation`, `runtime.py:224`) mas **não persistido** no `session_state`.
- **O5** — Sem **tabela relacional de eventos**: estado é JSONB monolítico em `amanda_sessions_v2`; impossível timeline/auditoria sem parsear JSONB.
- **O6** — Logs em **texto loguru** não estruturado (`app/logging.py`) → ingestão pelo Hub frágil.

### Financeiro
- **F1** — Tokens/custos **não persistidos** (só counter Prometheus em memória) → **zera no restart**, sem histórico (`runtime.py::_record_llm_cost`, `metrics.py:48-49`).
- **F2** — Custo **agregado global**, **não atribuível** por conversa / lead / mensagem.
- **F3** — Preço **hardcoded** `$0.40/$1.60` (`runtime.py:25-26`) → erro silencioso ao trocar modelo.
- **F4** — Custo do **Whisper não contabilizado** (`app/transcription.py` chama `whisper-1` sem registrar custo/duração).
- **F5** — `total_tokens` não exposto; `request_id` da OpenAI não capturado.
- **F6** — Sem scraper/retenção Prometheus garantidos no repo → série temporal não preservada.

### Comercial
- **C1** — **SEM integração Opportunities/Pipeline** GHL (`app/ghl/` cobre contacts/conversations/calendars/custom_values/tags — não há `opportunities.py`) → **comercial cego**: oportunidades, estágio, valor e vendas atribuíveis à IA = imensuráveis.
- **C2** — `opportunityId` nunca referenciado → impossível ligar atendimento da IA a venda.

### Risco transversal
- **R1** — Repo **SEM `.git` na VPS** (`/opt/zaf-autovip`) → rastreabilidade de deploy frágil. Registrar como risco de processo.

---

## 3. ADEQUAÇÕES NECESSÁRIAS

### Banco
- Criar tabela relacional de eventos `agent_events` (append-only) e tabela `llm_calls` (detalhe financeiro por turno), ambas no mesmo Postgres já existente (`amanda` DB). Não tocar no schema Agno (`amanda_sessions_v2`).
- Persistir `conversation_id` no `session_state` (preencher após `search_conversation` em `runtime.py:224`) para join conversa↔sessão↔CRM.
- Criar tabela `pricing` (ver Custos).

**Esboço `llm_calls`:**
```
id, ts, agent='amanda', contact_id, conversation_id, session_id,
model, request_id, input_tokens, output_tokens, total_tokens,
cost_usd, pricing_version, latency_ms, kind ('chat'|'whisper')
```

**Esboço `agent_events`:**
```
id, ts, agent='amanda', event_type, contact_id, conversation_id,
session_id, payload JSONB, cost_usd (nullable)
```

### Logs
- Migrar loguru para **JSON estruturado**: `logger.add(..., serialize=True)` em `app/logging.py` (sink de arquivo e/ou stdout). Manter rotação 10MB/7d.
- Padronizar campos: `contact_id`, `conversation_id`, `event`, `latency_ms` — já presentes nos placeholders atuais (`ghl_call`, `tool.call`, `runtime.run`).

### Tokens
- Em `runtime.py::_record_llm_cost`, além de alimentar Prometheus, **gravar uma linha em `llm_calls`** com `contact_id` + `conversation_id` + `session_id` + `model` + `request_id` + `input/output/total_tokens` + `latency_ms` (a latência já é medida em `runtime.py:281`).
- Capturar `request_id` da OpenAI a partir do `RunOutput`/resposta do Agno (investigar campo exato disponível) — registrar `NÃO IDENTIFICADO` se Agno não expuser, e usar fallback (hash do turno).
- Expor `total_tokens` (derivar input+output).

### Custos
- Substituir constantes `_PRICE_IN_PER_M/_PRICE_OUT_PER_M` (`runtime.py:25-26`) por **lookup na tabela `pricing`** por `model` + vigência:
```
pricing: model, price_in_per_m, price_out_per_m, price_per_minute (whisper),
         currency, valid_from, valid_to
```
- Versionar o preço usado (`pricing_version`) em cada linha de `llm_calls` → custo histórico reprodutível.

### Whisper
- Instrumentar `app/transcription.py::transcribe`: medir duração do áudio / segundos faturáveis, calcular custo via `pricing` (`whisper-1`), gravar linha `llm_calls` com `kind='whisper'` e emitir evento `WHISPER_TRANSCRIPTION`. Hoje só há log `whisper ok ... latency_ms`.

### CRM
- Persistir `conversation_id` (já em runtime) e os custom fields enviados no handoff (`dispatch.build_custom_fields`) como parte do evento `HANDOFF_CREATED`.

### Oportunidades
- Novo módulo `app/ghl/opportunities.py`: criar/atualizar oportunidade e ler estágio/valor (GHL `/opportunities`). Ligar `opportunity_id` ao `contact_id` no handoff. Emitir `OPPORTUNITY_LINKED`. **Maior esforço** — Fase 3.

---

## 4. ESTRATÉGIA DE INTEGRAÇÃO COM O HUB

A Amanda **já tem Postgres** — usar isso como ponto de integração primário:

- **Camada de eventos (pull):** tabelas `agent_events` + `llm_calls` no Postgres atual, lidas por um **coletor do Hub** (cursor por `id`/`ts` incremental). Fonte de verdade histórica, financeira e comercial.
- **Camada de tempo real (scrape):** **manter Prometheus** (`/metrics`) para latência/throughput/erros ao vivo. O Hub pode federar o endpoint. Não remover — complementa os eventos.
- **Contrato:** `agent="amanda"` em toda linha, `contact_id`/`conversation_id` como chaves de correlação. Schema de eventos padronizado para a frota (mesmos `event_type` entre agentes).
- **Sem broker:** dado o volume (SDR de uma loja), escrita síncrona/assíncrona no Postgres é suficiente; não introduzir Kafka/Redis nesta fase.

```
Amanda (FastAPI)
  ├─ Prometheus /metrics ──────────────→ Hub (scrape, tempo real)
  └─ Postgres
       ├─ agent_events  ─┐
       └─ llm_calls     ─┴──────────────→ Coletor do Hub (pull incremental)
```

---

## 5. EVENTOS RECOMENDADOS (mapeados ao código real)

Todos com `agent="amanda"`, `contact_id`, `conversation_id`, `session_id`, `ts`.

| Evento | Gatilho no código real | Dados | Já existe lógica? |
|---|---|---|---|
| `CONVERSATION_STARTED` | 1º turno do contato sem sessão prévia (`runtime.py` após load de `session_state`) | contact_id, conversation_id, ad_meta | Parcial (precisa flag de "primeira vez") |
| `CONVERSATION_COMPLETED` | `handoff.feito` setado (`tools.acionar_handoff`, `runtime.py:309`) | motivo, n_turnos, duração | ✅ lógica existe |
| `HANDOFF_CREATED` | `dispatch.execute_handoff` (`runtime.py:333`) | motivo, resumo, custom_fields, ramon_user_id | ✅ existe |
| `APPOINTMENT_CREATED` | `runtime._maybe_book_appointment` sucesso (`appointment_id` preenchido) | tipo, data_hora, appointment_id, calendar_id | ✅ existe |
| `FOLLOWUP_STARTED` / `FOLLOWUP_FINISHED` | **INEXISTENTE** hoje — só há reopen 24h (`_maybe_reopen`). Requer mecanismo proativo novo | reopen_count, motivo | ❌ não existe (só reopen) |
| `CONVERSATION_ABANDONED` | rota `POST /sessions/{contact_id}/abandon/{token}` (`webhook.py::abandon`) | motivo="abandonado" | ✅ existe |
| `LLM_CALL` | `runtime._record_llm_cost` (`runtime.py:282`) | model, input/output/total_tokens, request_id, cost_usd, pricing_version, latency_ms | Parcial (captura, não persiste) |
| `WHISPER_TRANSCRIPTION` | `transcription.transcribe` (`app/transcription.py`) | audio_seconds, cost_usd, latency_ms | ❌ não instrumentado |
| `LEAD_QUALIFIED` (dedup) | funil completo **1ª vez** (corrigir `runtime.py:265`) | intencao, funil | ⚠️ existe mas duplica |
| `OPPORTUNITY_LINKED` | novo `app/ghl/opportunities.py` (Fase 3) | opportunity_id, pipeline_stage, value | ❌ não existe |

> **Nota explícita:** `FOLLOWUP_*` é marcado como **não existente** — o agente só reabre após 24h sem outbound (`REOPEN_WINDOW`, `runtime.py:111`). Um follow-up proativo real (cutucar lead inativo) seria desenvolvimento novo.

---

## 6. PLANO DE EXECUÇÃO

### Fase 1 — Fundação financeira por conversa (esforço: Médio)
- Criar tabelas `pricing` + `llm_calls`.
- Persistir `conversation_id` no `session_state` (`runtime.py` pós `search_conversation`).
- `runtime._record_llm_cost`: gravar linha `llm_calls` por turno (tokens + custo + request_id + latência + atribuição contact/conversation).
- Substituir preço hardcoded (`runtime.py:25-26`) por lookup `pricing` + `pricing_version`.
- Instrumentar Whisper (`transcription.py`) → custo + `kind='whisper'`.
- **Entrega:** custo/token **atribuível por conversa e por lead**, com histórico. Fecha F1–F5.

### Fase 2 — Event log + logs JSON + correção operacional (esforço: Médio)
- Criar `agent_events` e emitir: CONVERSATION_STARTED/COMPLETED, HANDOFF_CREATED, APPOINTMENT_CREATED, CONVERSATION_ABANDONED, LLM_CALL, WHISPER_TRANSCRIPTION (reutilizar lógica existente).
- Migrar loguru para `serialize=True` (`app/logging.py`).
- Corrigir dedup de `amanda_qualificados_total` → emitir `LEAD_QUALIFIED` só na 1ª vez (flag no `session_state`).
- Contar conversas distintas (CONVERSATION_STARTED) vs turnos.
- **Entrega:** timeline relacional + logs ingeríveis. Fecha O1–O6, F6.

### Fase 3 — Camada comercial (esforço: Alto)
- Novo `app/ghl/opportunities.py` (criar/atualizar oportunidade, ler pipeline/estágio/valor).
- Ligar `opportunity_id` ao contato no handoff; emitir `OPPORTUNITY_LINKED`.
- (Opcional) Follow-up proativo real → `FOLLOWUP_STARTED/FINISHED`.
- **Entrega:** métricas comerciais e vendas atribuíveis à IA. Fecha C1–C2.

### Transversal
- Inicializar `git` em `/opt/zaf-autovip` e ligar a remoto → fecha R1.

---

## 7. RESUMO EXECUTIVO

A Amanda é o agente da frota **mais próximo de telemetria financeira madura**: já captura tokens (`runtime.py::_record_llm_cost`) e calcula custo (`runtime.py:45`), expondo 12 métricas Prometheus. O bloqueio não é fundação, é **persistência e atribuição**: hoje custo/token são agregados, efêmeros (zeram no restart) e não ligados a conversa/lead; o preço é hardcoded; Whisper não é contabilizado; e o lado comercial é cego (sem Opportunities). O caminho é gravar cada chamada de LLM/Whisper em tabelas Postgres (`llm_calls`, `agent_events`) já existentes no agente, ler por um coletor do Hub e manter Prometheus para tempo real. Fase 1 entrega custo por conversa; Fase 2, o event log + logs JSON + correção de duplicidade de qualificados; Fase 3, a integração de oportunidades. Esforço total: **Médio**, alavancado pela base já presente. Risco de processo: repo sem `.git` na VPS.

---

## 8. SCORE DE ADERÊNCIA AO HUB

| Dimensão | Baseline atual | Projetado (pós Fase 1-3) |
|---|---|---|
| Operacional | 6 | 9 |
| Financeiro | 4 | 9 |
| Comercial | 1 | 8 |
| Persistência/Eventos | 3 | 9 |
| Logs/Ingestão | 5 | 8 |
| **Nota global** | **~5,0 / 10** | **~8,5 / 10** |

**Justificativa baseline:** instrumentação acima da média (tokens + custo + métricas), mas agregada/efêmera, sem persistência relacional nem camada comercial.
**Justificativa projetada:** com `llm_calls` + `agent_events` + `pricing` + Opportunities, o agente passa a alimentar as três dimensões do Hub com histórico atribuível, mantendo Prometheus para tempo real. Classificação resultante: **🟢 Pronto para Integração**.

---

## ADENDO — Alinhamento de Frota v1 (decisões centrais, sobrepõem o acima)

### A. Contrato canônico de eventos
`agent_events` e `llm_calls` projetam o envelope do `CONTRATO_EVENTOS_CANONICO.md` (v1): `event_id`, `schema_version=1`, `event_type`, `client="autovip"`, `agent="amanda-autovip"`, `contact_id`, `conversation_id`, `occurred_at` (UTC), `payload`. `LLM_CALL`/`WHISPER` seguem §3.1/§3.2. Padronizar nomes de `component` ao vocabulário do contrato.

### B. Custo DUPLO em BRL (decisão da frota)
Amanda já calcula custo (vantagem) — manter cálculo no agente, **mas em BRL**: substituir o preço hardcoded `$0.40/$1.60` por tabela `pricing` com `price_*`, `usd_brl_rate`, `pricing_version`. Cada `LLM_CALL`/`WHISPER` grava `cost_usd` + `cost_brl` + tokens crus. Hub recalcula `hub_cost_brl` (reconciliação). Atualiza F3 e §3 Custos: alvo é BRL versionado, não USD agregado.

### C. Integração — transporte PULL SQL
Hub lê `agent_events`/`llm_calls` via Postgres por cursor. Adapter: `postgres_adapter.py` (registry `amanda-autovip`). Manter Prometheus para tempo real (complementar, não fonte financeira).

### D. LGPD — adiado para pós-MVP
Sem mascaramento de PII no MVP. Dívida técnica pós-MVP. (R1 — git na VPS — segue como recomendação, não bloqueio.)
