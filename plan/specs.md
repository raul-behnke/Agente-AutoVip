# Specs — Agente Amanda (Auto Vip)

Documento consolidado de decisões arquiteturais e técnicas geradas na sessão de grilling. Base para `/make-plan` e implementação.

Referência de negócio: [`plan/briefing.md`](./briefing.md).

---

## 1. Stack

| Componente | Escolha |
|---|---|
| Linguagem | Python 3.11 |
| Web framework | FastAPI + Uvicorn (async) |
| Agente | Agno (agente único) |
| LLM | OpenAI `gpt-4o-mini` |
| Transcrição | OpenAI Whisper (`whisper-1`) |
| DB | Postgres 16 + `pgvector` (image `pgvector/pgvector:pg16`) |
| Driver DB | `asyncpg` |
| HTTP client | `httpx` (async) |
| Retry | `tenacity` |
| Logs | `loguru` |
| Dev tunnel | `ngrok` |
| Deploy futuro | VPS (mesmo Docker compose) |

---

## 2. Integração GHL

### Credenciais

- **Location ID:** `fTgCQSx1OLWqid4XCWlY`
- **Private Integration Token (PIT):** `pit-REDACTED`
- **Base URL:** `https://services.leadconnectorhq.com`
- **Headers padrão:**
  - `Authorization: Bearer <PIT>`
  - `Version: 2021-04-15` (conversations/calendars) / `2021-07-28` (users)
  - `Accept: application/json`

### Usuários da Location

| Nome | userId | Papel |
|---|---|---|
| Ramon Isteban Garcia Raio | `0p5inF2cds3PmhFo6OjJ` | Vendedor principal (handoff target) |
| Maicon Porto | `9fItNR4lDoB9tvoqI1tX` | Admin / acompanhamento |
| Gabrieli da Auto Vip | `OdkMjKi2XTm0MjhBg5WX` | — |
| Raquel Aparecida Cavilia | `86En1jTDTkBpdlT3z8rz` | — |
| Suporte Integracoes | `AI6WhiMbluBEOX1vI1ID` | **Sender da Amanda** (`userId` no send-message) |

### Calendários

| Tipo | calendarId | Janela |
|---|---|---|
| Presencial (loja) | `yD3j7XQKHYvOU2Cqno3G` | Seg-Sex 9-18, Sáb 9-12 |
| Videochamada (WhatsApp) | `rbzX4QCNmp1jQcGhXNhU` | Seg-Sex 9-18, Sáb 9-12 |

Ambos: team member único = Ramon, slot 30min, autoConfirm `true`.

### Custom Values

- **FAQ (YAML):** `rfhXQLDpIq9bPgycN2fS`
  - Endpoint: `GET /locations/{locationId}/customValues/{id}`
  - Lido **on-demand** via tool `get_faq()` (sem cache).

### Tag de controle

- Tag: **`agent-ia`**
- Adicionada por Workflow GHL em novo lead (antes do disparo do webhook).
- Removida pela Amanda na tool `handoff_to_human` → workflow para de disparar.

### Endereço da loja

`Av. Irineu Bornhausen, 973 - São João, Itajaí - SC, 88305-001`

---

## 3. Fluxo de mensagens

### Inbound (cliente → Amanda)

1. Cliente envia msg WhatsApp.
2. Workflow GHL aguarda **12s** (debounce nativo) → dispara webhook.
3. Endpoint: `POST /webhook/inbound/YP-roJbtgU0XSUQiTb-TFr8mIu6lMzdm` (token 32-char no path).
4. FastAPI valida token, extrai `contactId`.
5. Cancela task em andamento para esse `contactId` (se houver e ainda **não** iniciou envio de blocos — ver §6).
6. Spawn nova task: refetcha conversa do GHL → roda turno Amanda.

### Pull da conversa

- `GET /conversations/search?locationId=...&contactId=...` → resolve `conversationId`.
- `GET /conversations/{id}/messages` → mensagens.
- **Concat:** todas mensagens `inbound` desde o último `outbound` da Amanda (fonte da verdade).
- Mensagens com attachment de áudio → Whisper transcribe antes de injetar como texto.
- Mensagens com attachments não-áudio (fotos) → não baixa, conta `{n} anexos recebidos` no input.

### Outbound (Amanda → cliente)

- LLM retorna structured output: `{"messages": ["bloco1", "bloco2", ...]}`.
- Cada bloco enviado via `POST /conversations/messages`:
  - `type: "SMS"`
  - `contactId`, `message`, `userId: AI6WhiMbluBEOX1vI1ID`.
- Delay sequencial entre blocos: **fixo 2s** (configurável `BLOCK_DELAY_MS`).
- Send retentado com tenacity 3x (1s/3s/9s) em falha.

---

## 4. Arquitetura do agente

### Agno

- **Agente único:** `Amanda` (sem Team).
- **Storage:** Agno `PostgresStorage` apenas para **`session_state`** (collected_data JSONB). `session_id = contactId`.
- **History:** **desligado** — histórico vem do fetch GHL a cada turno.
- **Model:** `OpenAIChat("gpt-4o-mini")` com structured output schema.

### Tools granulares (lista alvo)

| Tool | Função |
|---|---|
| `get_faq()` | Fetch Custom Value `rfhXQLDpIq9bPgycN2fS` |
| `update_lead_state(patch: dict)` | Merge no `session_state` (Postgres) |
| `transcribe_audio(url)` | Whisper → texto (chamada interna no pré-processamento, não pelo LLM) |
| `get_free_slots(calendar_id, start, end)` | `GET /calendars/{id}/free-slots` |
| `book_appointment(calendar_id, slot, contact_id, title, notes)` | `POST /calendars/events/appointments` |
| `add_contact_note(contact_id, body)` | `POST /contacts/{id}/notes` |
| `add_internal_comment(conversation_id, text_with_mention)` | `POST /conversations/messages` com `type: "InternalComment"` |
| `remove_tag(contact_id, tag)` | `POST /contacts/{id}/tags/remove` (ou DELETE conforme spec) |
| `handoff_to_human(reason, summary)` | Macro: `add_contact_note` + `add_internal_comment(@Ramon)` + `remove_tag("agent-ia")` |

Tools são granulares; `handoff_to_human` é o único macro composto (3 chamadas).

### System prompt

- Persona Amanda (§3-§4 briefing).
- Regras de não-resposta (preço/parcela/estoque, §27 briefing).
- Fluxo conversacional (§8-§15 briefing).
- Lista de gatilhos de handoff (§17 briefing) com diretiva: **"priorize completar coleta antes de escalonar, exceto se cliente demonstrar irritação"**.
- Lista de cidades próximas (§5).
- Endereço da loja.
- Horário comercial e copy condicional (§5).
- Schema do output: `{"messages": ["..."]}`.

---

## 5. Regras de negócio fixas

### Cidades próximas (visita presencial)

```
Itajaí, Navegantes, Balneário Camboriú, Camboriú, Ilhota, Penha, Itapema,
Porto Belo, Luiz Alves, Blumenau, Brusque, Gaspar, Pomerode, Bombinhas,
Balneário Piçarras, Barra Velha
```

Cidades fora dessa lista → oferecer videochamada.

### Horário comercial (afeta copy, não disponibilidade do agente)

- Atendimento Amanda: **24/7**.
- Janela comercial: Seg-Sex 9h-18h, Sáb 9h-12h, Dom fechado.
- Fora da janela: copy do handoff vira `"amanhã o consultor te chama"` (Amanda informa expectativa de retorno humano).

### Timezone

- `America/Sao_Paulo` (UTC-3, sem DST).
- Postgres armazena em UTC; conversão na borda (apresentação + booking).

### Follow-ups

- **Não implementados no agente.** CRM (Workflow GHL) cuida.

### Movimentação de pipeline / custom fields

- **Não usados.** Toda informação coletada vai para a nota de contato no handoff.

---

## 6. Concorrência e estado

### Cancel-on-new-webhook

- `active_tasks: dict[contactId, asyncio.Task]` em memória.
- Novo webhook para `contactId` com task ativa:
  - Se task **ainda não iniciou envio do 1º bloco** → `task.cancel()`, spawn nova.
  - Se task **já iniciou send_sms** → enfileira reprocessamento após série terminar.
- Point-of-no-return: **primeira chamada `POST /conversations/messages`** do array de blocos.

### Idempotência

- Dedup opcional por `messageId` (descarte se já processado nos últimos 60s).

### Locking multi-instância

- Single instance no MVP. Para multi-worker uvicorn futuro: Postgres advisory lock `pg_advisory_xact_lock(hashtext(contactId))`.

---

## 7. Persistência

### Schema mínimo

```sql
-- Agno gerencia esta tabela (PostgresStorage)
CREATE TABLE agno_sessions (
  session_id TEXT PRIMARY KEY,       -- = contactId GHL
  session_state JSONB,               -- collected_data
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
);

-- Opcional: debug
CREATE TABLE turn_logs (
  id BIGSERIAL PRIMARY KEY,
  contact_id TEXT,
  conversation_id TEXT,
  input_messages JSONB,
  output_blocks JSONB,
  tools_called JSONB,
  latency_ms INT,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### `session_state` (collected_data) — campos

```jsonc
{
  "nome": "",
  "cidade": "",
  "veiculo_interesse": "",
  "intencao": "troca|a_vista|financiamento|carta_credito|nao_identificado",
  "troca": {
    "modelo": "", "ano": "", "km": "",
    "quitado": null, "fotos_recebidas": 0
  },
  "financiamento": {
    "cpf": "", "nascimento": "",
    "entrada": "", "parcela_desejada": "",
    "possui_cnh": null
  },
  "carta_credito": { "contemplada": null },
  "agendamento": {
    "tipo": "presencial|video|null",
    "data_hora": null,
    "appointment_id": null
  },
  "pendencias": [],
  "handed_off": false,
  "handoff_reason": null,
  "handoff_at": null,
  "anexos_recebidos": 0,
  "tentativas_pergunta": {}   // campo -> contador (cap 3 por briefing §16)
}
```

---

## 8. Segurança

- Webhook protegido por token 32-char no path: `YP-roJbtgU0XSUQiTb-TFr8mIu6lMzdm`.
- Token comparado com `secrets.compare_digest`.
- Sem CORS público.
- Secrets em `.env`, nunca commitados.

---

## 9. Observabilidade

- Loguru estruturado: stdout + arquivo rotativo (`logs/amanda.log`).
- Campos por log: `contact_id`, `conversation_id`, `turn_id`, `event`, `latency_ms`.
- Tabela `turn_logs` opcional (ver §7).

---

## 10. Resiliência

- Todas chamadas GHL/OpenAI envoltas em `tenacity.retry(stop_after_attempt=3, wait_exponential(multiplier=1, min=1, max=9))`.
- Em falha final: log `ERROR` com `traceId` GHL quando disponível; turno aborta sem enviar bloco parcial.

---

## 11. Setup local

- `docker-compose.yml`: serviço `postgres` (pgvector image), volume nomeado, porta 5432.
- `.env` com: `GHL_PIT`, `GHL_LOCATION_ID`, `OPENAI_API_KEY`, `DATABASE_URL`, `WEBHOOK_TOKEN`, `SENDER_USER_ID`, `RAMON_USER_ID`, `CAL_PRESENCIAL_ID`, `CAL_VIDEO_ID`, `FAQ_CUSTOM_VALUE_ID`, `LOJA_ENDERECO`, `BLOCK_DELAY_MS=2000`.
- `ngrok http 8000` → cola URL no Workflow GHL.

---

## 12. Workflow GHL (do lado do CRM)

### Workflow 1 — New lead
- Trigger: contact criado / tag de origem ad.
- Ação: Add Tag `agent-ia`.

### Workflow 2 — Inbound message
- Trigger: Inbound Message.
- Filtro: contato tem tag `agent-ia`.
- Wait: **12s** (debounce).
- Ação: Webhook → `POST https://<ngrok>/webhook/inbound/YP-roJbtgU0XSUQiTb-TFr8mIu6lMzdm`.
- Payload mínimo: `contact_id`.

---

## 13. Pendências do cliente (Auto Vip)

- [ ] Preencher YAML do FAQ no Custom Value `rfhXQLDpIq9bPgycN2fS` (temas em §26 do briefing).
- [ ] Configurar os 2 Workflows GHL (§12).
- [ ] Confirmar/criar tag `agent-ia` no sub-account.
- [ ] Rotacionar chave OpenAI exposta nesta sessão.

---

## 14. Fora de escopo (MVP)

- Estoque dinâmico Revenda Mais.
- Envio/análise de fotos.
- Apresentação automática de veículos.
- Follow-ups automáticos pelo agente.
- Movimentação de pipeline pelo agente.
- Multi-location / OAuth marketplace.
- Custom fields no GHL.

Possíveis para v2 (§35 briefing).
