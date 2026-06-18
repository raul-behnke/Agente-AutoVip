# RELATÓRIO DE APLICAÇÃO — ADEQUAÇÃO DE TELEMETRIA (AMANDA / AUTO VIP)

> Execução do `PLANO_ADEQUACAO_TELEMETRIA_AUTOVIP.md` (Fases 1, 2 e 3).
> Branch: `feat/telemetria-hub-fase1`.
> Escopo: instrumentação para alimentar o **ZOI Performance Hub**.
> Data: 2026-06-17. Status: **código aplicado, validado em sintaxe e em testes isolados de módulo** (app completo roda em Docker na VPS — não executado neste ambiente).

---

## 1. RESUMO

As três fases do plano foram implementadas. A telemetria deixou de ser **agregada e efêmera** (só Prometheus em memória) e passou a ser **persistida e atribuível por conversa/lead**, com event log relacional, preço versionado em tabela, custo de Whisper contabilizado, logs em JSON e integração comercial (Opportunities) no handoff.

Validação possível neste ambiente (sem `agno`/`psycopg` instalados):
- `python -m py_compile` em todos os arquivos alterados → **OK**.
- Import isolado de `app.telemetry`, `app.pricing`, `app.amanda.state_schema` em venv com `sqlalchemy` → **OK**.
- Cálculo de custo: chat 1000/500 tok = `$0.0012`; whisper 12,5s = `$0.00125` → **correto**.
- Fallback de preço resiliente sem DB → **OK**.
- `ensure_keys` mescla as novas chaves de telemetria em sessões antigas → **OK**.

---

## 2. ARQUIVOS

### Novos
| Arquivo | Função |
|---|---|
| `app/telemetry/__init__.py` | API pública: `record_llm_call`, `emit_event`, `init_telemetry_schema` |
| `app/telemetry/db.py` | Engine SQLAlchemy dedicado + DDL de `llm_calls`, `agent_events`, `pricing` |
| `app/telemetry/events.py` | Gravação async tolerante a falha (via `asyncio.to_thread`) |
| `app/pricing.py` | Lookup de preço por modelo + seed + cache + fallback |
| `app/ghl/opportunities.py` | Endpoints GHL Opportunities (search/create/update) |

### Editados
| Arquivo | Mudança |
|---|---|
| `app/amanda/agent.py` | `MODEL_ID` como fonte única do modelo |
| `app/amanda/runtime.py` | `_record_llm_cost` async (Prometheus + `llm_calls`); persiste `conversation_id`; emite eventos; `_link_opportunity` |
| `app/transcription.py` | Whisper instrumentado (duração via `verbose_json` + custo + `llm_calls`) |
| `app/orchestrator/concat.py` | Propaga `contact_id`/`conversation_id` até `transcribe` |
| `app/amanda/state_schema.py` | `conversation_id`, `opportunity_id`, bloco `telemetry{}` no state |
| `app/config.py` | `ghl_pipeline_id`, `ghl_pipeline_stage_id` |
| `app/logging.py` | Sink de arquivo em JSON (`serialize=True`) |
| `app/webhook.py` | Evento `CONVERSATION_ABANDONED` na rota `/abandon` |
| `app/main.py` | Bootstrap de schema + seed de pricing no lifespan |
| `.env.example` | `GHL_PIPELINE_ID`, `GHL_PIPELINE_STAGE_ID` |

---

## 3. FASE 1 — FUNDAÇÃO FINANCEIRA POR CONVERSA

**Tabelas criadas** (`app/telemetry/db.py`, criadas no startup, idempotente):
- **`llm_calls`** — `id, ts, agent, contact_id, conversation_id, session_id, model, kind(chat|whisper), request_id, input_tokens, output_tokens, total_tokens, audio_seconds, cost_usd, pricing_version, latency_ms`.
- **`pricing`** — `model, price_in_per_m, price_out_per_m, price_per_minute, currency, version, valid_from, valid_to`. Seed: `gpt-4.1-mini` ($0.40/$1.60), `whisper-1` ($0.006/min).

**Custo atribuível** (`app/amanda/runtime.py::_record_llm_cost`): agora `async`, grava uma linha em `llm_calls` por turno com `contact_id` + `conversation_id` + `session_id` + tokens + custo + `pricing_version` + `latency_ms`, além de alimentar Prometheus. Tokens extraídos do `RunOutput` do Agno; `request_id` capturado best-effort (`_extract_request_id`).

**Preço via tabela** (`app/pricing.py`): substituiu o hardcode `_PRICE_IN_PER_M/_PRICE_OUT_PER_M`. `cost_chat`/`cost_whisper` retornam `(custo, pricing_version)`. Cache em memória com fallback se DB indisponível.

**Whisper contabilizado** (`app/transcription.py`): `response_format="verbose_json"` fornece a duração faturável; custo gravado em `llm_calls` com `kind='whisper'` e atribuição por conversa (propagada via `concat.py`).

**conversation_id persistido**: gravado em `session_state["conversation_id"]` no início do turno (antes só existia em runtime).

**Gaps fechados:** F1, F2, F3, F4, F5, O4.

---

## 4. FASE 2 — EVENT LOG + LOGS JSON + DEDUP

**Tabela `agent_events`** (append-only): `id, ts, agent, event_type, contact_id, conversation_id, session_id, payload(JSONB), cost_usd`.

**Eventos emitidos** (mapeados ao código real):
| Evento | Gatilho |
|---|---|
| `CONVERSATION_STARTED` | 1ª vez sem sessão prévia ou após reopen (`runtime`) |
| `LEAD_QUALIFIED` | funil completo — **1ª vez por conversa** (dedup) |
| `LLM_CALL` | persistido em `llm_calls` (Fase 1) |
| `WHISPER_TRANSCRIPTION` | persistido em `llm_calls` kind=whisper (Fase 1) |
| `APPOINTMENT_CREATED` | `_maybe_book_appointment` com `appointment_id` |
| `HANDOFF_CREATED` | bloco de handoff (`execute_handoff`) |
| `CONVERSATION_COMPLETED` | handoff — dedup por `telemetry.completed_emitted` |
| `CONVERSATION_ABANDONED` | rota `/sessions/{id}/abandon` |

**Dedup de qualificados** (O2/O9): `amanda_qualificados_total` agora incrementa **uma vez por conversa** (flag `telemetry.qualified_emitted` no state), em vez de a cada turno.

**Logs JSON** (O6): sink de arquivo com `serialize=True` em `app/logging.py`. stdout permanece legível para operação.

**Flags de controle no state** (`state_schema.telemetry{started_emitted, qualified_emitted, completed_emitted}`) garantem emissão única e sobrevivem a restart (persistidas pelo Agno).

**Gaps fechados:** O2, O5, O6, O9, F6 (estrutura pronta para retenção via coletor).

> **Follow-up**: confirmado **inexistente** como conceito próprio — só há reopen 24h (`_maybe_reopen`). `FOLLOWUP_STARTED/FINISHED` **não** implementados (exigiriam mecanismo proativo novo). Registrado como pendência.

---

## 5. FASE 3 — CAMADA COMERCIAL (OPPORTUNITIES)

**Módulo `app/ghl/opportunities.py`**: `search_opportunity`, `create_opportunity`, `update_opportunity` (GHL `/opportunities`, version `2021-07-28`).

**Vínculo no handoff** (`runtime._link_opportunity`): no encerramento, reusa a oportunidade existente do contato ou cria uma nova no pipeline configurado; persiste `opportunity_id` no state; emite `OPPORTUNITY_CREATED` (criação) ou `OPPORTUNITY_UPDATED` (reuso) — ver §8b.3. **Best-effort e idempotente** — se `GHL_PIPELINE_ID` vazio, é pulado sem quebrar o handoff.

**Config nova**: `GHL_PIPELINE_ID`, `GHL_PIPELINE_STAGE_ID` (`config.py` + `.env.example`).

**Gaps fechados:** C1, C2 — *condicionado a preencher os IDs de pipeline/estágio no `.env` de produção*.

---

## 6. INTEGRAÇÃO COM O HUB

- **Pull (histórico):** coletor do Hub lê `llm_calls` + `agent_events` por cursor incremental (`id`/`ts`). Toda linha tem `agent="amanda"` e `contact_id`/`conversation_id` para correlação.
- **Scrape (tempo real):** Prometheus `/metrics` mantido — não removido.
- Telemetria **nunca derruba o atendimento**: todas as escritas são `try/except` + `asyncio.to_thread`.

---

## 7. PENDÊNCIAS / RISCOS

| Item | Observação |
|---|---|
| **Execução real** | App não rodado aqui (sem `agno`/`psycopg` no ambiente). Validar em staging na VPS antes de produção |
| **`request_id` OpenAI** | Best-effort — depende do Agno expor no `RunOutput`; pode ficar `NULL` |
| **Pipeline IDs** | Fase 3 só ativa após preencher `GHL_PIPELINE_ID`/`GHL_PIPELINE_STAGE_ID` em produção |
| **Endpoints Opportunities** | Verificar contrato exato (paths/campos) contra a conta GHL antes de ligar |
| **Follow-up proativo** | Não implementado (só reopen 24h) — desenvolvimento futuro |
| **R1 — repo sem `.git` na VPS** | Branch local criado (`feat/telemetria-hub-fase1`); falta inicializar git/remoto na VPS e definir fluxo de deploy |
| **Retenção** | Coletor/retention do Hub é responsabilidade da plataforma ZOI |

---

## 8. SCORE DE ADERÊNCIA

| Dimensão | Antes | Depois (aplicado) |
|---|---|---|
| Operacional | 6 | 9 |
| Financeiro | 4 | 9 |
| Comercial | 1 | 8* |
| Persistência/Eventos | 3 | 9 |
| Logs/Ingestão | 5 | 8 |
| **Global** | **~5,0 / 10** | **~8,5 / 10** |

\* Comercial atinge 8 **após** configurar os IDs de pipeline em produção; sem isso, ~5.

**Classificação:** 🟢 **Pronto para Integração** (pós validação em staging + config de pipeline).

---

## 8b. CORREÇÕES v2 — ALINHAMENTO AO CONTRATO CANÔNICO

> Rodada de correção após validação central contra `CONTRATO_EVENTOS_CANONICO.md` (v1, schema_version=1). Não regrediu nada da v1 (custo por conversa, Whisper `verbose_json`, logs JSON, dedup, Opportunities best-effort, `pricing_version`).

### 8b.1 Envelope canônico (gap 1)
`llm_calls` e `agent_events` (`app/telemetry/db.py`) ganharam o envelope obrigatório, preenchido em `app/telemetry/events.py` (`_envelope()`):
- `event_id` — `uuid4()` (`String(36)`, `UNIQUE NOT NULL`) → idempotência; Hub deduplica por este campo.
- `schema_version` — `INTEGER` default `1` (`db.py::SCHEMA_VERSION`).
- `client` — `"autovip"` (`db.py::CLIENT_SLUG`).
- `agent` — slug corrigido de `amanda` → **`amanda-autovip`** (`db.py::AGENT_SLUG`).

### 8b.2 Custo em BRL (gap 2)
- `pricing` ganhou `usd_brl_rate` (`db.py`; seed 5.40 em `app/pricing.py`).
- `cost_chat`/`cost_whisper` agora retornam **`(cost_usd, cost_brl, usd_brl_rate, pricing_version)`** (`app/pricing.py`).
- `llm_calls` ganhou `cost_brl` + `usd_brl_rate` (já tinha `pricing_version`); callers atualizados em `app/amanda/runtime.py::_record_llm_cost` e `app/transcription.py`.
- `agent_events` ganhou `cost_brl`; `emit_event` aceita `cost_brl`.
- Whisper passou a faturar por **minuto arredondado pra cima** (`math.ceil`, CONTRATO §6).
- Tokens crus (`input/output/total_tokens`) seguem gravados → Hub recalcula e reconcilia.

### 8b.3 Vocabulário de evento (gap 3)
`runtime._link_opportunity` (`app/amanda/runtime.py`): `OPPORTUNITY_LINKED` foi removido. Agora emite:
- **`OPPORTUNITY_CREATED`** na criação (payload: `opportunity_id`, `pipeline_id`, `stage_id`, `motivo`).
- **`OPPORTUNITY_UPDATED`** no reuso (payload idem + `status`).

### 8b.4 Validação v2 (isolada)
- `py_compile` OK em todos os arquivos.
- Envelope presente em ambas as tabelas; `event_id` = uuid4 (36 chars).
- `agent/client` = `amanda-autovip`/`autovip`.
- Custo: chat 1000/500 tok → `cost_usd=$0.0012`, `cost_brl=R$0.00648` (×5.40). Whisper 75s → `ceil(75/60)=2 min` → `$0.012` / `R$0.0648`. **Correto.**

### 8b.5 Exemplo de `LLM_CALL` (linha de `llm_calls` no envelope canônico)
```json
{
  "event_id": "b3a1e9c2-7f4d-4a18-9c66-2e0d5a1b8f30",
  "schema_version": 1,
  "event_type": "LLM_CALL",
  "client": "autovip",
  "agent": "amanda-autovip",
  "contact_id": "ghl_abc123",
  "conversation_id": "ghl_conv_789",
  "payload": {
    "component": "agent",
    "model": "gpt-4.1-mini",
    "input_tokens": 1000,
    "output_tokens": 500,
    "total_tokens": 1500,
    "cost_usd": 0.0012,
    "cost_brl": 0.00648,
    "usd_brl_rate": 5.40,
    "pricing_version": "2025-01-baseline",
    "latency_ms": 1840
  }
}
```
> Nota: `llm_calls` é uma tabela colunar (campos no nível da linha, não aninhados em `payload`); o adapter PULL SQL do Hub projeta esses campos para o `payload` canônico de `LLM_CALL` na exportação. `request_id` permanece best-effort.

---

## 8c. ENDPOINT /export + DEPLOY EM PRODUÇÃO

> Runbook `DEPLOY_AUTOVIP.txt` §4-5. Transporte PULL HTTP para o Hub.

### Endpoint (`app/export_router.py`)
- `GET /export/events?since=<cursor>&sig=<hmac>&limit=<n>` — registrado em `app/main.py`.
- Auth: `sig = HMAC-SHA256(ZOI_EXPORT_SECRET, since)` hex; `compare_digest`. Sem/errada → **401**. Secret não configurado → **503**.
- Resposta: `{"events":[<envelope canônico>], "next_cursor":<id>}`. Idempotência por `event_id`, cursor por `id`.
- `occurred_at` derivado de `agent_events.ts` (ISO UTC). `conversation_id` cai pra `contact_id` se nulo.
- Config: `ZOI_EXPORT_SECRET` (dedicado, ≠ webhook) + `EXPORT_TABLE` (`app/config.py`).

### LLM_CALL/WHISPER no event log
`app/telemetry/events.py::record_llm_call` agora, além de `llm_calls`, emite também `LLM_CALL`/`WHISPER_TRANSCRIPTION` em `agent_events` (payload §3.1/§3.2) → o `/export` sobre `agent_events` cobre todo o stream canônico.

### Deploy (produção VPS2 — 2026-06-18)
- Backup: pasta + `pg_dump amanda.sql` (3.7M) + baseline. Rollback pronto.
- rsync (preservou `.env`), `ZOI_EXPORT_SECRET` gerado (`openssl rand -hex 32`, 64 chars, ≠ webhook).
- `docker compose -f docker-compose.prod.yml up -d --build app`.
- **Smoke OK:** health `{"status":"ok"}`; `/export` sem sig→401, sig errada→401, HMAC válido→200; envelope validado com evento sintético (`event_id`, `schema_version=1`, `client=autovip`, `agent=amanda-autovip`, `occurred_at`, payload com tokens+`cost_brl`+`usd_brl_rate`+`pricing_version`); `next_cursor` avança; sintético removido.
- Webhook GHL inalterado; volume Postgres preservado.

---

## 9. PRÓXIMOS PASSOS

1. Subir branch em staging na VPS; rodar migração (tabelas criam-se no startup) e processar conversas reais.
2. Conferir contrato dos endpoints GHL Opportunities e preencher `GHL_PIPELINE_ID`/`GHL_PIPELINE_STAGE_ID`.
3. Apontar o coletor do Hub para `llm_calls` + `agent_events`.
4. Inicializar `git` em `/opt/zaf-autovip` (fecha R1).
5. (Futuro) Implementar follow-up proativo real.
