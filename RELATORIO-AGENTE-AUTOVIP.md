# RELATÓRIO TÉCNICO — AGENTE "AMANDA" (AUTO VIP)

> Análise para integração ao Dashboard Centralizado de Performance de Agentes (ZOI).
> Base: código-fonte do repositório `/opt/zaf-autovip` (VPS), espelhado localmente.
> Data da análise: 2026-06-17.

---

# 1. IDENTIFICAÇÃO DO PROJETO

| Campo | Valor |
|---|---|
| **Nome do Projeto** | Amanda — Auto Vip Agent |
| **Cliente** | Auto Vip (loja de veículos, Itajaí - SC) |
| **Versão** | App `0.3.0` (`app/main.py`) / pacote `0.1.0` (`pyproject.toml`) — **divergência de versionamento** |
| **Ambiente** | Produção (container `autovip_app_prod` na VPS2 `147.79.87.179`) |
| **Repositório** | `/opt/zaf-autovip` na VPS — **SEM `.git`** (nenhum versionamento remoto no diretório) |
| **Responsável Técnico** | NÃO IDENTIFICADO no código. Owner do handoff humano: "Ramon" (`RAMON_USER_ID=0p5inF2cds3PmhFo6OjJ`) |

**Resumo Executivo:**
Agente de WhatsApp (SDR/qualificação de leads) para loja de veículos. Recebe mensagens via webhook do GoHighLevel (GHL), processa com LLM da OpenAI (Agno framework), qualifica o lead por um funil de coleta (nome, cidade, intenção, dados de troca/financiamento), responde em "bolhas" estilo humano e, ao completar a coleta ou em gatilhos específicos, faz handoff para um consultor humano (nota no contato GHL + remoção de tag). Persiste **estado de sessão** em Postgres (via Agno) e expõe métricas Prometheus em `/metrics`. As **conversas em si vivem no GHL**, não no banco local.

---

# 2. STACK TECNOLÓGICA

| Camada | Tecnologia |
|---|---|
| **Backend** | Python 3.11, FastAPI, Uvicorn |
| **Frontend** | NÃO IDENTIFICADO (existe `index-form.html` solto na raiz, não servido pelo app) |
| **Banco de Dados** | PostgreSQL 16 (imagem `pgvector/pgvector:pg16`) |
| **ORM** | SQLAlchemy + `psycopg` v3 (gerenciado internamente pelo Agno; sem models próprios) |
| **Framework de IA** | **Agno** (`agno.agent.Agent`) |
| **LLM Provider** | OpenAI |
| **Modelos Utilizados** | `gpt-4.1-mini` (chat, temp 0.6) + `whisper-1` (transcrição de áudio) |
| **Serviços Externos** | GoHighLevel / LeadConnector (CRM + WhatsApp), OpenAI |
| **Infraestrutura** | Docker Compose (`autovip_app_prod` + `autovip_postgres_prod`), Nginx reverse proxy + Certbot (TLS) |
| **Hospedagem** | VPS Hostinger-like, IP `147.79.87.179`, domínio `autovip.appzoi.com.br` → `127.0.0.1:8002` → container `8000` |
| **Filas** | NÃO IDENTIFICADO. Concorrência via `asyncio.Task` em memória (`active_tasks`, `pending_reprocess`) — **não há broker** |
| **Cache** | Apenas caches in-process (FAQ, transcrições). Sem Redis/Memcached |
| **Storage** | Volume Docker `pgdata`. Logs em arquivo rotativo (`logs/amanda.log`, loguru, 10MB/7 dias) |

---

# 3. ARQUITETURA GERAL

**Fluxo completo de atendimento:**

1. **Entrada** — GHL Workflow dispara `POST /webhook/inbound/{token}` (`app/webhook.py`). Valida token (`secrets.compare_digest`), extrai `contact_id`, aplica **gate de tag** (`agente-ia`/`agent-ia`): sem a tag → noop 200.
2. **Disparo assíncrono** — `asyncio.create_task(handle_inbound(...))`. Resposta imediata `{"ok": true}` ao GHL. Dedup/cancelamento de turnos concorrentes por contato (`handle_inbound`).
3. **Coleta de contexto** — `process_turn` busca a conversa no GHL (`/conversations/search`), puxa as últimas 50 mensagens, extrai os inbounds pendentes (desde o último outbound), transcreve áudios (Whisper) e monta o histórico (`orchestrator/concat.py`).
4. **Estado** — carrega `session_state` do Postgres via Agno (`amanda_sessions_v2`), aplica reabertura (janela 24h) e seed de metadados do anúncio.
5. **Processamento (LLM)** — `agent.arun(...)` com instruções, 8 runs de histórico, state no contexto e **8 tools** (registrar info, FAQ, pendência, agendar, handoff etc.). Saída estruturada `TurnReply` (lista de bolhas).
6. **Pós-processamento** — `enforce_bubbles` (anti-eco, máx. 1 pergunta/turno, dedup, ≤3 bolhas).
7. **Side-effects** — se houver `agendamento.confirmado` → reserva no calendário GHL; se `handoff.feito` → nota no contato + mention do consultor + atualização de custom fields + remoção da tag.
8. **Resposta** — `sender.send_blocks` envia cada bolha como SMS/WhatsApp via GHL (`POST /conversations/messages`), com delay entre bolhas.
9. **Persistência** — Agno grava `session_state` (JSONB) no Postgres. Métricas atualizadas no registry Prometheus.

**Diagrama textual:**

```
WhatsApp (lead)
   ↓
GoHighLevel (Workflow + tag agente-ia)
   ↓  POST /webhook/inbound/{token}
FastAPI (app.webhook)              → 200 {"ok":true} imediato
   ↓  asyncio.create_task
Runtime (app.amanda.runtime.process_turn)
   ↓  GET conversa + mensagens
GoHighLevel Conversations API ──→ (transcrição Whisper p/ áudio)
   ↓  session_state (load)
Postgres (amanda_sessions_v2 / Agno)
   ↓  agent.arun
OpenAI gpt-4.1-mini  (+ tools)
   ↓  TurnReply (bolhas) → enforce_bubbles
   ├─→ Calendário GHL (book_appointment)        [se agendou]
   ├─→ Contato GHL (note + custom fields + tag)  [se handoff]
   ↓  send_blocks
GoHighLevel Conversations (outbound) → WhatsApp (lead)
   ↓
Prometheus /metrics  +  Postgres session_state (save)
```

---

# 4. BANCO DE DADOS

| Campo | Valor |
|---|---|
| **Tipo** | PostgreSQL 16 (pgvector) |
| **Host** | `autovip_postgres_prod` (container, porta interna 5432). String do app: `postgresql+psycopg://amanda:amanda@postgres:5432/amanda`. `.env` local aponta `localhost:5434` |
| **Quantidade de tabelas** | **2 tabelas lógicas declaradas** pelo app, ambas gerenciadas pelo Agno. O schema interno é criado/migrado pelo próprio Agno (não há DDL no repo) |

**Tabelas declaradas** (`app/amanda/agent.py`):

### Tabela: `amanda_sessions_v2`
- **Finalidade:** Persistência de sessão do agente Agno (histórico de runs + `session_state`).
- **Campos principais:** `session_id` (= `contact_id` do GHL), `session_type`, `session_data` (JSONB contendo `session_state`), histórico de runs/mensagens do agente, timestamps. Estrutura exata definida pelo Agno.
- **`session_state` (JSONB)** — shape em `app/amanda/state_schema.py`: `lead{nome,cidade,regiao}`, `intencao`, `veiculo_interesse`, `troca{...}`, `financiamento{cpf,data_nascimento,entrada,parcela_desejada,cnh}`, `vista_confirmado`, `carta_credito_contemplada`, `pendencias[]`, `agendamento{tipo,data_hora,appointment_id,confirmado,oferecido}`, `handoff{feito,motivo}`, `stage`, `counters{...}`, `last_asked[]`, `ad_meta{}`.
- **Relacionamentos:** chave de junção lógica = `contact_id` (também é `session_id` e `user_id`). Sem FKs explícitas no repo.

### Tabela: `amanda_memories_v2`
- **Finalidade:** Tabela de memórias do Agno (memória de longo prazo). **Não há evidência de uso ativo** (sem chamadas de memória no código).
- **Campos principais:** Estrutura Agno padrão. NÃO IDENTIFICADO uso no fluxo.
- **Relacionamentos:** por `user_id`/`session_id`.

**Mapeamento de armazenamento por domínio:**

| Domínio | Onde está | Observação |
|---|---|---|
| **Conversas** | **GHL** (não no Postgres local) | App lê via API; nada de conversa é persistido localmente |
| **Mensagens** | **GHL** + parcialmente no histórico de runs do Agno | Texto bruto das mensagens vive no GHL |
| **Leads** | `session_state.lead` (JSONB) + GHL (custom fields) | Espelhado no contato GHL no handoff |
| **Contatos** | **GHL** | `contact_id` é a identidade |
| **Atendimentos** | `session_state.stage` / `handoff` (JSONB) | Estado, não tabela relacional |
| **Agendamentos** | `session_state.agendamento` (JSONB) + Calendário GHL | `appointment_id` referencia o evento GHL |
| **Logs** | Arquivo `logs/amanda.log` (loguru) + stdout do container | **Não há tabela de logs** |
| **Tokens** | **NÃO armazenados em banco** | Só contador Prometheus em memória (ver §7) |
| **Custos** | **NÃO armazenados em banco** | Só contador Prometheus em memória (ver §7) |

> **Conclusão crítica:** o banco local guarda **estado de sessão**, não um histórico relacional consultável de conversas/mensagens/tokens/custos. Para um dashboard, a fonte de verdade de conversas é o **GHL**, e tokens/custos hoje são **efêmeros** (Prometheus).

---

# 5. CONVERSAS E ATENDIMENTOS

**Como uma conversa é criada:** A conversa **não é criada pelo agente** — ela já existe no GHL. O agente apenas a localiza (`conversations.search_conversation(contact_id)`). A **sessão local** (`amanda_sessions_v2`) é criada implicitamente pelo Agno no primeiro `agent.arun` para aquele `contact_id`.

**Como uma conversa é encerrada:** Logicamente, via `handoff.feito = True` (tool `acionar_handoff` ou rota `/sessions/{contact_id}/abandon/{token}`). Define `stage="fechado"` e a partir daí turnos seguintes são ignorados (`result="terminal"`) — exceto **reabertura** automática após 24h sem outbound (`_maybe_reopen`).

**Campos utilizados:**

| Campo | Presença |
|---|---|
| `conversationId` | **SIM** — obtido em runtime via `search_conversation`, **não persistido** no state |
| `contactId` | **SIM** — identidade central (= `session_id` = `user_id`) |
| `locationId` | **SIM** — `GHL_LOCATION_ID` (fixo por env: `fTgCQSx1OLWqid4XCWlY`) |
| `opportunityId` | **NÃO IDENTIFICADO** — o agente **não cria nem referencia oportunidades** |

**Critérios encontrados (eventos/registros que identificam cada situação):**

| Situação | Como identificar | Onde |
|---|---|---|
| **Atendimento iniciado** | Métrica `amanda_turns_total{result="run"}` incrementa; log `runtime.run` | `runtime.py` |
| **Atendimento concluído** | `session_state.handoff.feito == True`; métrica `amanda_handoff_total{motivo}` | `tools.acionar_handoff` / `runtime` |
| **Handoff** | Tool `acionar_handoff` (motivos: irritacao, pedido_humano, coleta_completa, agendamento_confirmado, simulacao_solicitada, fora_escopo, lead_nao_respondeu); nota criada no contato GHL; tag `agente-ia` removida | `dispatch.execute_handoff` |
| **Agendamento** | `session_state.agendamento.confirmado == True` + `data_hora`; evento criado no Calendário GHL (`appointment_id` preenchido) | `runtime._maybe_book_appointment` |
| **Follow-up** | **NÃO IDENTIFICADO como evento próprio.** Existe **reabertura** (reopen) após 24h sem outbound (`counters.reopen`), mas não um mecanismo de follow-up proativo agendado | `runtime._maybe_reopen` |
| **Encerramento** | `stage="fechado"` + `handoff.feito`; ou rota `/abandon` (motivo `abandonado`) | `webhook.abandon` / `tools` |
| **Qualificado** | Funil sem campos faltantes no início do turno → `amanda_qualificados_total` | `runtime` + `state_schema.missing_fields` |

---

# 6. INTEGRAÇÃO COM GHL / CRM

| Campo | Valor |
|---|---|
| **Integração utilizada** | GoHighLevel / LeadConnector REST API (`https://services.leadconnectorhq.com`) |
| **OAuth ou API Key** | **Private Integration Token (PIT)** — `Authorization: Bearer {GHL_PIT}`. **Não usa OAuth** |
| **Versionamento** | Header `Version` por chamada (`2021-04-15`, `2021-07-28`) |

**Endpoints utilizados (todos os encontrados):**

| Método | Endpoint | Finalidade | Arquivo |
|---|---|---|---|
| GET | `/conversations/search` | Achar conversa do contato | `ghl/conversations.py` |
| GET | `/conversations/{id}/messages` | Puxar mensagens (limit 50) | `ghl/conversations.py` |
| POST | `/conversations/messages` | Enviar resposta (type SMS) | `ghl/conversations.py` |
| POST | `/contacts/{id}/notes` | Nota de handoff / resumo | `ghl/contacts.py` |
| PUT | `/contacts/{id}` | Atualizar custom fields | `ghl/contacts.py` |
| DELETE | `/contacts/{id}/tags` | Remover tag de gate (`agente-ia`) | `ghl/contacts.py` |
| GET | `/calendars/{id}/free-slots` | Slots livres (declarado; uso indireto) | `ghl/calendars.py` |
| POST | `/calendars/events/appointments` | Agendar visita | `ghl/calendars.py` |
| GET | `/locations/{locationId}/customValues/{id}` | FAQ canônico (YAML em Custom Value) | `ghl/custom_values.py` |

**Cobertura por área:**

| Área | Chamada existe? | Detalhe |
|---|---|---|
| **Contatos** | SIM | notes, custom fields, tags |
| **Conversas** | SIM | search, messages, send |
| **Oportunidades** | **NÃO** | nenhuma chamada a `/opportunities` |
| **Calendários** | SIM | free-slots + book appointment |
| **Pipelines** | **NÃO** | NÃO IDENTIFICADO |
| **Custom Fields** | SIM | 8 IDs mapeados (CPF, nascimento, veículo interesse, entrada, veículo/modelo/ano/km de troca) — `dispatch._CF` |
| **Tags** | SIM (parcial) | apenas **remoção** da tag de gate; não adiciona tags |

**Dados enviados ao GHL:** mensagens de resposta (texto), nota de handoff (resumo da coleta + mention `@Ramon (userId:...)`), custom fields preenchidos, remoção de tag, evento de agendamento (título, início/fim, status `confirmed`).
**Dados recebidos do GHL:** payload do webhook (contact_id, tags, custom fields de anúncio como "VEÍCULO DE INTERESSE"/"ANO"), conversa/mensagens (corpo, direction, dateAdded, attachments), free-slots, FAQ (Custom Value YAML).

---

# 7. TOKENS E CUSTOS OPENAI

**Os tokens são armazenados?** → **NÃO** (não persistidos). São **contabilizados em memória** via Prometheus, mas perdidos a cada restart do processo e **não atribuíveis por conversa**.

**Onde (em memória, runtime):**
- Arquivo: `app/amanda/runtime.py` → função `_record_llm_cost(result)`.
- Fonte: `result.metrics.input_tokens` / `result.metrics.output_tokens` (objeto `RunOutput` do Agno).
- Destino: contadores Prometheus globais em `app/metrics.py`.

| Item | Status |
|---|---|
| **Tabela** | NÃO EXISTE (sem persistência de tokens) |
| **input_tokens** | Capturado → `amanda_llm_tokens_total{kind="input"}` (counter agregado) |
| **output_tokens** | Capturado → `amanda_llm_tokens_total{kind="output"}` (counter agregado) |
| **total_tokens** | **Não exposto diretamente** (derivável de input+output) |
| **Modelo utilizado** | `gpt-4.1-mini` (hardcoded em `agent.py`) |
| **Preço configurado** | **Hardcoded** em `runtime.py`: input `$0.40`/1M, output `$1.60`/1M tokens |

**Existe cálculo de custo?** → **SIM**, em memória (não persistido por conversa). Resultado vai para `amanda_llm_cost_usd_total` (counter Prometheus global agregado).

**Fórmula encontrada** (`runtime.py:45`):
```
custo_usd = (input_tokens  / 1_000_000) × 0.40
          + (output_tokens / 1_000_000) × 1.60
```

> **Limitações para dashboard:**
> 1. Custo do **Whisper** (transcrição de áudio) **não é contabilizado**.
> 2. Métricas são **agregadas globais** (counter), **não há custo/token por conversa, por lead ou por dia** sem um scraper Prometheus externo (Prometheus + recording rules / time-series).
> 3. Sem `total_tokens` persistido nem `request_id` da OpenAI.
> 4. Preço hardcoded — se trocar de modelo, cálculo fica errado silenciosamente.

---

# 8. LOGS E TELEMETRIA

| Item | Detalhe |
|---|---|
| **Sistema de logs** | **loguru** (`app/logging.py`) |
| **Arquivos** | `logs/amanda.log` — rotação 10MB, retenção 7 dias, compressão zip; + stdout (capturado pelo Docker) |
| **Tabelas de log** | NÃO EXISTEM |
| **Ferramentas externas** | **Prometheus** (exposição em `GET /metrics`). Não há Grafana/Sentry/OpenTelemetry no repo |

**Métricas Prometheus expostas** (`app/metrics.py`):
`amanda_turns_total{result}`, `amanda_handoff_total{motivo}`, `amanda_qualificados_total`, `amanda_bubble_violations_total{kind}`, `amanda_tool_calls_total{name}`, `amanda_aluc_rejects_total`, `amanda_llm_latency_seconds`, `amanda_llm_tokens_total{kind}`, `amanda_llm_cost_usd_total`, `amanda_openai_quota_errors_total`, `amanda_ghl_latency_seconds{path}`, `amanda_ghl_errors_total{status}`.

**Checklist de históricos:**

| Histórico | Existe? | Localização | Estrutura / Campos |
|---|---|---|---|
| **Mensagens** | SIM (parcial) | GHL (fonte) + `amanda_sessions_v2` (runs do Agno) | corpo, direction, dateAdded, attachments (GHL); mensagens de run (Agno JSONB) |
| **Execução** | SIM | `logs/amanda.log` + métricas | linhas `runtime.run`, `runtime.terminal`, `tool.call name=... latency_ms=...`; counters por resultado |
| **Erros** | SIM | `logs/amanda.log` + `amanda_turns_total{result="error"}` + `amanda_ghl_errors_total`, `amanda_openai_quota_errors_total` | stacktrace via loguru; counters |
| **Chamadas OpenAI** | SIM (parcial) | `logs/amanda.log` (latência `amanda_llm_latency_seconds`) + tokens/custo agregados | **sem log estruturado por chamada com tokens** — só agregado Prometheus e latência |

> **Observação:** logs são **texto não estruturado** (loguru com placeholders), não JSON. Parsing para dashboard exigiria regex/ingestão. Métricas Prometheus são a via estruturada, mas **sem um Prometheus rodando + retenção, não há série histórica** — NÃO IDENTIFICADO scrape configurado no repo.

---

# 9. MÉTRICAS POSSÍVEIS (sem alterar código)

## Operacionais

| Métrica | Disponível | Fonte | Confiabilidade |
|---|---|---|---|
| Conversas iniciadas | SIM | `amanda_turns_total{result="run"}` (turnos, não conversas únicas) | Média (conta turnos, não conversas distintas) |
| Conversas concluídas | SIM | `amanda_handoff_total` | Alta |
| Handoffs | SIM | `amanda_handoff_total{motivo}` | Alta |
| Follow-ups | PARCIAL | `counters.reopen` no JSONB (não exposto em métrica) | Baixa |
| Agendamentos | SIM | `amanda_handoff_total{motivo="agendamento_confirmado"}` + Calendário GHL | Alta (cruzando com GHL) |
| Abandono | PARCIAL | rota `/abandon` (motivo `abandonado`) — só se o CRM chamar | Baixa |
| Qualificados | SIM | `amanda_qualificados_total` | Média (conta por turno completo, pode duplicar) |
| Turnos com erro | SIM | `amanda_turns_total{result="error"}` | Alta |
| Latência LLM / GHL | SIM | `amanda_llm_latency_seconds`, `amanda_ghl_latency_seconds` | Alta |

## Financeiras

| Métrica | Disponível | Fonte | Confiabilidade |
|---|---|---|---|
| Tokens (total agregado) | SIM | `amanda_llm_tokens_total{kind}` | Média (efêmero, zera no restart) |
| Custos OpenAI (agregado) | SIM | `amanda_llm_cost_usd_total` | Média (sem Whisper; preço hardcoded) |
| Custo por conversa | **NÃO** | sem atribuição por `contact_id` | — |
| Custo por mensagem | **NÃO** | sem atribuição por mensagem | — |

## Comerciais

| Métrica | Disponível | Fonte | Confiabilidade |
|---|---|---|---|
| Oportunidades criadas | **NÃO** | agente não integra `/opportunities` | — |
| Oportunidades atualizadas | **NÃO** | idem | — |
| Vendas atribuíveis à IA | **NÃO** | sem ligação com pipeline/venda GHL | — |
| Custom fields preenchidos (proxy de qualificação) | SIM (via GHL) | `PUT /contacts/{id}` no handoff | Média |

---

# 10. GAPS PARA O DASHBOARD DE PERFORMANCE

| # | GAP | Impacto | Criticidade |
|---|---|---|---|
| 1 | **Tokens/custos não persistidos** (só Prometheus em memória, zera no restart) | Sem histórico financeiro confiável | **Alta** |
| 2 | **Custo/token não atribuível por conversa/lead** | Impossível custo por atendimento/ROI por lead | **Alta** |
| 3 | **Sem integração com Oportunidades/Pipeline GHL** | Nenhuma métrica comercial / vendas atribuíveis à IA | **Alta** |
| 4 | **`conversationId` não persistido** | Dificulta join conversa↔sessão↔CRM | Média |
| 5 | **Sem tabela relacional de mensagens/eventos** (estado é JSONB monolítico) | Consultas analíticas exigem ler GHL ou parsear JSONB | **Alta** |
| 6 | **Logs não estruturados** (texto loguru, não JSON) | Ingestão para dashboard cara/frágil | Média |
| 7 | **Sem Prometheus/scraper configurado no repo** | Métricas existem mas não há série histórica retida | **Alta** |
| 8 | **Sem eventos de domínio explícitos** (handoff/agendamento existem só como counter + JSONB) | Falta event log para auditoria/timeline | Média |
| 9 | **Custo do Whisper não contabilizado** | Subestima custo real de áudio | Média |
| 10 | **Preço OpenAI hardcoded** | Erro silencioso se trocar modelo | Baixa |
| 11 | **`amanda_qualificados_total` conta por turno** (pode duplicar mesmo lead) | Métrica de qualificação inflada | Média |
| 12 | **Reopen/follow-up sem evento próprio** | Follow-up não mensurável | Baixa |
| 13 | **Versão divergente** (`0.3.0` app vs `0.1.0` pyproject) e repo **sem `.git`** | Rastreabilidade/deploy frágil | Média |

---

# 11. RECOMENDAÇÕES DE INSTRUMENTAÇÃO

Eventos a serem emitidos (idealmente para uma tabela `agent_events` append-only e/ou stream para o dashboard), todos com `contact_id`, `conversation_id`, `session_id`, `timestamp`, `agent="amanda"`:

| Evento | Motivo | Dados necessários | Complexidade |
|---|---|---|---|
| `AGENT_TURN_STARTED` | Contar turnos/conversas distintas | contact_id, conversation_id, input_chars | Baixa |
| `MESSAGE_RECEIVED` | Volume inbound, mídia | contact_id, kind (text/audio/photo), n_chars | Baixa |
| `MESSAGE_SENT` | Volume outbound, nº de bolhas | contact_id, n_bubbles, n_chars | Baixa |
| `LLM_CALL` | **Custo/token por conversa** (gap #1/#2) | contact_id, model, input_tokens, output_tokens, cost_usd, latency_ms, request_id | Média |
| `TRANSCRIPTION` | Custo Whisper (gap #9) | contact_id, audio_seconds/chars, cost_usd | Baixa |
| `LEAD_FIELD_CAPTURED` | Funil de qualificação detalhado | contact_id, campo, valor | Baixa |
| `LEAD_QUALIFIED` | Qualificação **única** por lead | contact_id, intencao, funil completo | Baixa |
| `HANDOFF_CREATED` | Conversões para humano | contact_id, motivo, resumo | Baixa (já existe lógica) |
| `APPOINTMENT_CREATED` | Agendamentos confirmados | contact_id, tipo, data_hora, appointment_id | Baixa (já existe lógica) |
| `FOLLOWUP_STARTED` / `_FINISHED` | Medir reaberturas/follow-up | contact_id, reopen_count, motivo | Média |
| `OPPORTUNITY_LINKED` | Métrica comercial (gap #3) | contact_id, opportunity_id, pipeline_stage, value | **Alta** (exige integrar `/opportunities`) |
| `CONVERSATION_CLOSED` | Encerramento e duração | contact_id, motivo, duração, n_turnos | Baixa |
| `ERROR` / `OPENAI_QUOTA` | Saúde operacional | contact_id, tipo, mensagem | Baixa |

**Recomendações de plataforma:** persistir esses eventos em Postgres (tabela própria) **e** manter Prometheus + Grafana com retenção; emitir logs em **JSON estruturado** (loguru `serialize=True`); adicionar `request_id` da OpenAI; mover preços para configuração por modelo.

---

# 12. SCORE DE OBSERVABILIDADE

| Dimensão | Nota (0-10) | Justificativa |
|---|---|---|
| **Banco de Dados** | 4 | Persiste estado de sessão (JSONB), mas sem modelo relacional de conversas/eventos/tokens; tabela de memória ociosa |
| **Logs** | 6 | loguru com rotação e boa cobertura de pontos quentes, porém **não estruturado** (texto), sem tabela |
| **Custos** | 3 | Fórmula existe e roda, mas **efêmera**, agregada, sem Whisper, sem atribuição por conversa |
| **CRM** | 7 | Integração GHL sólida (contatos, conversas, calendário, custom fields), mas **sem oportunidades/pipeline** |
| **Conversas** | 5 | Rastreáveis via GHL + estado, mas sem `conversationId` persistido nem histórico relacional local |
| **Telemetria** | 6 | 12 métricas Prometheus bem pensadas, mas **sem scraper/retenção** garantidos no repo |
| **Monitoramento** | 4 | `/health` e `/metrics` existem; sem alerting, sem dashboards, sem tracing distribuído |

**Nota Final: 5.0 / 10**

**Justificativa:** O agente tem **fundação de telemetria acima da média** (métricas Prometheus, fórmula de custo, logs com latência por tool/GHL), mas tudo é **agregado e efêmero**. Falta a camada de **persistência analítica** (eventos por conversa, tokens/custo atribuíveis, integração comercial) que um Dashboard de Performance exige. As métricas operacionais são imediatamente aproveitáveis; as financeiras e comerciais **não**, sem instrumentação adicional.

---

# 13. RESUMO EXECUTIVO FINAL

A Amanda é um agente SDR de WhatsApp para a Auto Vip, construído em FastAPI + Agno + OpenAI (`gpt-4.1-mini` + Whisper), integrado ao GoHighLevel como CRM/canal. O fluxo é: webhook do GHL → gate por tag → coleta de contexto (mensagens + transcrição) → LLM com 8 tools → resposta em bolhas → side-effects (agendamento no calendário GHL, handoff com nota + custom fields + remoção de tag). O estado da sessão é persistido em Postgres como JSONB (via Agno); as conversas em si vivem no GHL.

**Já pode ser medido (operacional):** turnos, handoffs por motivo, agendamentos confirmados, qualificações, violações de formatação, chamadas de tool, latências de LLM e de GHL, erros e falhas de quota — tudo via Prometheus, desde que haja um scraper com retenção.

**Não pode ser medido hoje:** custo/token **por conversa ou por lead** (só agregado e efêmero), métricas **comerciais** (oportunidades, pipeline, vendas atribuíveis — sem integração), histórico relacional de mensagens/eventos, e custo de transcrição.

**Principais riscos:** tokens/custos zeram no restart (Prometheus em memória); repositório **sem `.git`** na VPS (rastreabilidade de deploy frágil); logs não estruturados; preço OpenAI hardcoded; nenhuma fila/broker (concorrência só em memória).

**Principais oportunidades:** emitir um event log persistente (`agent_events`) cobrindo LLM_CALL, HANDOFF, APPOINTMENT, QUALIFIED e OPPORTUNITY_LINKED; integrar `/opportunities` do GHL para fechar o ciclo comercial; serializar logs em JSON; subir Prometheus+Grafana com retenção. A base de instrumentação já existente reduz bastante o esforço.

**Esforço estimado para integração ao Dashboard:**
- Operacional (consumir métricas atuais): **Baixo** (1–2 semanas, infra Prometheus + dashboards).
- Financeiro (custo por conversa persistido): **Médio** (instrumentar `LLM_CALL`/`TRANSCRIPTION` + tabela de eventos).
- Comercial (oportunidades/vendas): **Alto** (nova integração GHL `/opportunities` + atribuição).

**Classificação Final: 🟡 Requer Ajustes**
A arquitetura é sólida e bem instrumentada para o operacional, mas exige uma camada de **persistência de eventos** e **integração comercial** antes de alimentar um Dashboard de Performance completo. Não requer reestruturação; requer instrumentação incremental.
