# Plano de Implementação — Agente Amanda (Auto Vip)

Plano em fases consecutivas, cada uma executável em chat novo. Base: [`plan/specs.md`](./specs.md) e [`plan/briefing.md`](./briefing.md).

**Working dir:** `/Users/raulbehnke/zaf-autovip`

---

## Phase 0 — Documentation Discovery

**Objetivo:** confirmar APIs reais (não assumidas) antes de codar. Resultado vira `plan/allowed-apis.md`.

### Tarefas

1. **Agno framework** (`https://docs.agno.com`)
   - Ler: `/agents/overview`, `/agents/storage`, `/agents/sessions`, `/agents/state`, `/agents/structured-output`, `/agents/tools`, `/models/openai`.
   - Extrair (com link/seção):
     - Construtor `Agent(...)` — params suportados (model, storage, tools, instructions, response_model, add_history_to_messages).
     - `PostgresStorage` — params (db_url, table_name, schema, mode), método `upgrade_schema()`.
     - `session_id` e `session_state` — como ler/escrever no decorrer do turno, persistência automática.
     - `Agent.arun()` vs `Agent.run()` — async signature, retorno.
     - Como passar **histórico externo** como `messages=[...]` no run (sem usar storage history).
     - Structured output: usar `response_model: pydantic.BaseModel` ou JSON mode.
     - Tools: decorator vs classe; suporte async; como acessar `session_state` de dentro da tool.
     - Integração `OpenAIChat` — params `id`, `api_key`, `temperature`.

2. **GHL endpoints** (`https://marketplace.gohighlevel.com/docs/ghl/...`)
   - Listar shape exato (request body, headers, path, response) de:
     - `GET /conversations/search` — params `locationId`, `contactId`.
     - `GET /conversations/{conversationId}/messages` — paginação, campos `direction` (inbound/outbound), `attachments[]`, `dateAdded`, `body`, `type`.
     - `POST /conversations/messages` — body para `type: "SMS"` (contactId, message, userId) e `type: "InternalComment"` (conversationId, message com `@username<userId>...</userId>`).
     - `GET /locations/{locationId}/customValues/{id}` — auth, shape resposta.
     - `GET /calendars/{calendarId}/free-slots` — params `startDate`, `endDate` (epoch ms), `timezone`.
     - `POST /calendars/events/appointments` — body (calendarId, locationId, contactId, startTime, endTime, title, appointmentStatus).
     - `POST /contacts/{contactId}/notes` — body `body`, `userId` (opcional).
     - Remover tag: `DELETE /contacts/{contactId}/tags` com body `{tags:[...]}` OU `POST /contacts/{contactId}/tags/remove` — confirmar qual existe.
   - Confirmar header `Version` por endpoint (varia 2021-04-15 vs 2021-07-28).

3. **OpenAI**
   - Confirmar `whisper-1` endpoint (`/audio/transcriptions`) — formato multipart, params `model`, `file`, `language=pt`.
   - `gpt-4o-mini` — structured output via `response_format={"type":"json_schema",...}` ou via Agno wrapper.

### Output

Criar `plan/allowed-apis.md` com:
- Por endpoint/método: assinatura exata, headers obrigatórios, body de exemplo testado, link da doc.
- Lista "**Anti-patterns**": métodos que NÃO existem (ex: se `tags/remove` não existir, marcar), params deprecados.
- Snippets prontos pra copiar (ex: chamada httpx para cada endpoint).

### Verificação Phase 0

- [ ] `plan/allowed-apis.md` existe.
- [ ] Cada endpoint tem URL + link doc.
- [ ] Cada API Agno usada tem versão confirmada (`pip show agno`).
- [ ] Smoke test (curl) feito em pelo menos: search conversation, get messages, send SMS, get custom value, get free slots — pra confirmar que PIT autoriza.

---

## Phase 1 — Bootstrap do projeto

**Objetivo:** estrutura de pastas, dependências, Docker Postgres, `.env`, FastAPI vazio rodando.

### Tarefas

1. Criar layout:
   ```
   /Users/raulbehnke/zaf-autovip/
   ├── app/
   │   ├── __init__.py
   │   ├── main.py              # FastAPI app
   │   ├── config.py            # pydantic-settings
   │   ├── logging.py           # loguru setup
   │   ├── ghl/                 # cliente GHL (httpx + tenacity)
   │   │   ├── __init__.py
   │   │   ├── client.py
   │   │   ├── conversations.py
   │   │   ├── contacts.py
   │   │   ├── calendars.py
   │   │   └── custom_values.py
   │   ├── agent/
   │   │   ├── __init__.py
   │   │   ├── amanda.py        # construção do Agent Agno
   │   │   ├── prompt.py        # system prompt
   │   │   ├── schema.py        # pydantic response_model
   │   │   └── tools.py         # tools granulares
   │   ├── orchestrator/
   │   │   ├── __init__.py
   │   │   ├── runner.py        # cancel-on-new-webhook
   │   │   ├── concat.py        # extrai inbounds desde último outbound
   │   │   └── sender.py        # envio em blocos com delay
   │   ├── transcription.py     # Whisper
   │   └── webhook.py           # endpoint inbound
   ├── docker-compose.yml
   ├── pyproject.toml
   ├── .env.example
   ├── .gitignore
   ├── README.md
   ├── plan/                    # já existe
   └── logs/                    # rotativo
   ```

2. `pyproject.toml` com deps:
   ```
   fastapi, uvicorn[standard], httpx, tenacity, loguru, pydantic-settings,
   agno, openai, asyncpg, sqlalchemy[asyncio], psycopg[binary], pgvector,
   python-multipart, pytz
   ```

3. `docker-compose.yml`:
   ```yaml
   services:
     postgres:
       image: pgvector/pgvector:pg16
       environment:
         POSTGRES_USER: amanda
         POSTGRES_PASSWORD: amanda
         POSTGRES_DB: amanda
       ports: ["5432:5432"]
       volumes: ["pgdata:/var/lib/postgresql/data"]
   volumes: { pgdata: {} }
   ```

4. `.env.example` com todas as vars da seção 11 do specs.

5. `app/config.py` carregando `.env` via `pydantic_settings.BaseSettings`.

6. `app/logging.py`: loguru sink stdout + `logs/amanda.log` rotativo 10MB/7d.

7. `app/main.py`: FastAPI minimal com `/health` retornando 200.

8. `README.md` com passos `docker compose up -d && uvicorn app.main:app --reload`.

### Verificação Phase 1

- [ ] `docker compose up -d` sobe Postgres.
- [ ] `psql postgresql://amanda:amanda@localhost:5432/amanda -c "CREATE EXTENSION IF NOT EXISTS vector;"` ok.
- [ ] `uvicorn app.main:app --reload` sobe sem erro.
- [ ] `curl localhost:8000/health` → 200.

### Anti-patterns

- Não criar `requirements.txt` em paralelo com `pyproject.toml`.
- Não commitar `.env`.

---

## Phase 2 — Cliente GHL (httpx + retry)

**Objetivo:** módulo `app/ghl/` com todas as chamadas tipadas, testadas via smoke script.

### Tarefas

1. `app/ghl/client.py`:
   - `AsyncClient` httpx único (singleton via lifespan FastAPI).
   - Wrapper `request()` com tenacity (3 tentativas, exp backoff 1-9s).
   - Headers padrão injetados; permite override de `Version` por endpoint.
   - Log estruturado de cada call (URL, status, latency, traceId).

2. `app/ghl/conversations.py`:
   - `search_conversation(contact_id) -> conversation_id` (`GET /conversations/search`).
   - `get_messages(conversation_id, limit=50) -> list[Message]` com dataclass tipada.
   - `send_sms(contact_id, message)` → POST com `type:"SMS"`, `userId=SENDER_USER_ID`.
   - `add_internal_comment(conversation_id, text)` → POST com `type:"InternalComment"`.

3. `app/ghl/contacts.py`:
   - `add_note(contact_id, body)`.
   - `remove_tag(contact_id, tag)` — usar endpoint confirmado na Phase 0.

4. `app/ghl/calendars.py`:
   - `get_free_slots(calendar_id, start_iso, end_iso, tz="America/Sao_Paulo")`.
   - `book_appointment(calendar_id, contact_id, start_iso, end_iso, title, notes)`.

5. `app/ghl/custom_values.py`:
   - `get_custom_value(value_id) -> str` (retorna `value` raw, YAML será parseado na tool).

6. **Smoke script** `scripts/smoke_ghl.py`:
   - Roda cada função contra um contato real de teste.
   - Imprime resultado. Deve passar antes de prosseguir.

### Verificação Phase 2

- [ ] `python scripts/smoke_ghl.py` retorna sucesso em todas as chamadas.
- [ ] Falha simulada (URL errada) dispara 3 retries no log.

### Documentação a citar

- Usar exclusivamente endpoints/payloads listados em `plan/allowed-apis.md`.

### Anti-patterns

- Não usar `requests` síncrono.
- Não criar funções com params não documentados.
- Não hardcodar `locationId` em cada função — vem de config.

---

## Phase 3 — Whisper + concat de mensagens

**Objetivo:** transcrever áudios e produzir o "input do turno" como string única.

### Tarefas

1. `app/transcription.py`:
   - `transcribe(audio_url: str) -> str` usando OpenAI `audio.transcriptions.create(model="whisper-1", file=..., language="pt")`.
   - Download via httpx, upload via multipart.
   - Cache opcional em memória `{url: text}` por execução.

2. `app/orchestrator/concat.py`:
   - `extract_pending_inbounds(messages: list) -> list[ProcessedMessage]`:
     - Inverte iteração até encontrar última `direction=outbound` da Amanda.
     - Coleta inbounds posteriores em ordem cronológica.
   - `build_turn_input(processed: list) -> str`:
     - Para cada msg: texto direto OU transcrição do attachment de áudio OU `[Cliente enviou {n} foto(s)]`.
     - Concatena com `\n`.

### Verificação Phase 3

- [ ] Teste unitário com fixture: 3 inbounds + 1 outbound antigo → retorna só os 3 últimos.
- [ ] Áudio de teste transcrito retorna string PT.

### Anti-patterns

- Não rodar Whisper em sync dentro de endpoint async (use `await client.audio...`).
- Não fazer transcrição se attachment não for áudio.

---

## Phase 4 — Agente Amanda (Agno)

**Objetivo:** construir o `Agent` Agno com tools, structured output, session_state em Postgres.

### Tarefas

1. `app/agent/schema.py`:
   ```python
   from pydantic import BaseModel
   class AmandaResponse(BaseModel):
       messages: list[str]  # blocos a enviar
   ```

2. `app/agent/prompt.py`:
   - System prompt completo (specs §4 + briefing §3-§17, §27).
   - Inserir lista de cidades próximas, endereço, horário comercial.
   - Diretiva: "Priorize completar a coleta antes de escalonar, exceto em caso de irritação."
   - Diretiva: "Fora do horário comercial (Seg-Sex 9-18, Sáb 9-12), no handoff use copy: 'amanhã o consultor te chama'. Dentro: 'o consultor já vai te chamar'."

3. `app/agent/tools.py`:
   - Cada tool é função async decorada (`@tool` Agno conforme Phase 0).
   - Tools: `get_faq`, `update_lead_state`, `get_free_slots`, `book_appointment`, `add_contact_note`, `add_internal_comment`, `remove_tag`, `handoff_to_human`.
   - `handoff_to_human(reason, summary)` → executa nota + internal comment com `@username<userId>0p5inF2cds3PmhFo6OjJ</userId>` + remove tag `agent-ia` + marca `session_state.handed_off=True`.
   - Tools acessam `session_state` conforme padrão Agno descoberto na Phase 0.

4. `app/agent/amanda.py`:
   - `build_amanda_agent() -> Agent` factory.
   - `OpenAIChat("gpt-4o-mini", api_key=...)`.
   - `PostgresStorage(db_url, table_name="agno_sessions")`.
   - `response_model=AmandaResponse`.
   - `add_history_to_messages=False` (histórico vem do GHL).
   - Tools registradas.
   - System prompt do `prompt.py`.

5. Função `run_turn(contact_id, turn_input, history_messages) -> AmandaResponse`:
   - `await agent.arun(message=turn_input, session_id=contact_id, messages=history_messages)`.
   - Retorna parsed pydantic.

### Verificação Phase 4

- [ ] Smoke: `await run_turn("test123", "Oi quero saber do HB20", [])` retorna `AmandaResponse` com pelo menos 1 mensagem.
- [ ] `session_state` persiste em `agno_sessions` (verificar SQL).
- [ ] Tool `get_faq` retorna conteúdo do Custom Value real.

### Anti-patterns

- Não usar `Agent.run()` (sync) em código async.
- Não inventar params Agno — só usar os confirmados na Phase 0.
- Não logar `session_state` com PII em produção (CPF/nascimento).

---

## Phase 5 — Orchestrator (cancel + sender em blocos)

**Objetivo:** gerenciar concorrência por `contactId` e enviar blocos com delay.

### Tarefas

1. `app/orchestrator/sender.py`:
   - `async def send_blocks(contact_id, blocks: list[str], delay_ms=2000)`:
     - Para cada bloco: `await ghl.send_sms(contact_id, block)` → `await asyncio.sleep(delay_ms/1000)`.
     - Marca flag `sending_started=True` no início (para gating de cancel).

2. `app/orchestrator/runner.py`:
   - `active_tasks: dict[str, asyncio.Task] = {}`.
   - `sending_flags: dict[str, bool] = {}`.
   - `async def handle_inbound(contact_id):`
     1. Se existe task ativa e `sending_flags[contact_id]` é `False` → `task.cancel()`.
     2. Se `sending_flags[contact_id]` é `True` → enfileira reprocessamento via `pending_reprocess: set[str]`.
     3. Spawn `asyncio.create_task(process_turn(contact_id))`.
   - `async def process_turn(contact_id)`:
     1. Resolve `conversation_id` (search).
     2. Fetch messages.
     3. Extract pending inbounds (Phase 3).
     4. Build turn input.
     5. `run_turn(...)` (Phase 4).
     6. Set `sending_flags[contact_id]=True`.
     7. `send_blocks(...)`.
     8. Set flag `False`, limpa task.
     9. Se `contact_id in pending_reprocess` → re-spawn.
   - Tratamento de `CancelledError` no passo 1-5: log + cleanup.

### Verificação Phase 5

- [ ] Teste: dispara 3 chamadas `handle_inbound` em <1s → só 1 envio acontece, com último input agregado.
- [ ] Teste: dispara `handle_inbound` durante `send_blocks` → enfileira e reprocessa após.

### Anti-patterns

- Não usar threads — tudo asyncio.
- Não bloquear o webhook esperando turno terminar (retorna 200 imediatamente).

---

## Phase 6 — Endpoint webhook + integração final

**Objetivo:** wire-up FastAPI → orchestrator → Amanda → GHL.

### Tarefas

1. `app/webhook.py`:
   - `POST /webhook/inbound/{token}`:
     - `secrets.compare_digest(token, settings.WEBHOOK_TOKEN)` → senão 401.
     - Parse body → extrai `contact_id` (campo varia conforme payload Workflow GHL; confirmar na Phase 0 / dev manual).
     - `asyncio.create_task(handle_inbound(contact_id))`.
     - Retorna `{"ok": true}` 200 imediatamente.

2. `app/main.py`:
   - Registra `webhook.router`.
   - Lifespan: cria httpx client, conecta Postgres, builda Agno agent singleton.
   - Shutdown: fecha httpx, aguarda tasks ativas com timeout 30s.

3. README com passos:
   - `docker compose up -d`
   - `uvicorn app.main:app --reload`
   - `ngrok http 8000`
   - Cola URL + token no Workflow GHL.

### Verificação Phase 6

- [ ] curl POST no endpoint com token errado → 401.
- [ ] curl POST com token correto e contact_id de teste → 200 + log mostrando ciclo completo (search → fetch → LLM → send).
- [ ] WhatsApp real: cliente manda "oi" → Amanda responde em blocos.

### Anti-patterns

- Não processar o turno dentro do handler do webhook (timeout).
- Não logar o body inteiro do webhook se contiver dados sensíveis sem mascarar CPF.

---

## Phase 7 — Verificação end-to-end

**Objetivo:** validar fluxos do briefing num contato de teste.

### Cenários (rodar manualmente via WhatsApp em contato com tag `agent-ia`)

1. **Saudação + nome/cidade** — cliente "oi" → Amanda se apresenta, pergunta nome+cidade.
2. **Troca completa** — fornecer modelo, ano, km, quitado, fotos → state correto.
3. **Financiamento** — CPF, nascimento, entrada, parcela, CNH → coletados.
4. **À vista** — handoff rápido.
5. **Carta crédito** — pergunta contemplada, handoff.
6. **Irritação** — cliente xinga → handoff imediato sem completar coleta.
7. **Pergunta de preço** — Amanda não responde valor, registra dúvida.
8. **Fora FAQ** — handoff.
9. **Agendamento presencial** — cidade Itajaí → Amanda sugere slot real do calendário, agenda.
10. **Agendamento vídeo** — cidade Curitiba → sugere videochamada.
11. **Áudio** — cliente manda voice note → transcrita.
12. **Fotos** — cliente manda 3 fotos → contador incrementa, Amanda confirma recebimento.
13. **Mensagens fragmentadas** — 3 msgs em <12s → 1 resposta agregada.
14. **Burst durante envio** — cliente manda durante envio de blocos → reprocessa após.
15. **Fora hora comercial** — handoff usa copy "amanhã".
16. **Pós-handoff** — após handoff, novas msgs do cliente não disparam Amanda (tag removida).

### Verificações automatizadas (grep/SQL)

- [ ] `grep -r "requests\." app/` → vazio (só httpx async).
- [ ] `grep -r "time.sleep" app/` → vazio (asyncio.sleep).
- [ ] `psql ... -c "SELECT session_state FROM agno_sessions LIMIT 5"` → JSON válido com campos do schema.
- [ ] Nota criada no GHL no contato de teste (verificar via API).
- [ ] InternalComment com `@username<userId>0p5inF2cds3PmhFo6OjJ</userId>` aparece no inbox.

### Saída esperada

- Tudo verde → projeto MVP entregue.
- Issues encontradas → criar `plan/issues.md` e iterar.

---

## Notas de execução

- **Cada fase abre num chat novo.** Cada agente executor lê `plan/specs.md` + `plan/allowed-apis.md` + a fase atual.
- Pendências do cliente (FAQ YAML, Workflows GHL, rotação OpenAI key) podem rodar em paralelo — não bloqueiam Phase 0-6, só Phase 7.
- Pendência crítica antes de Phase 7: **2 Workflows GHL configurados** (add tag + inbound webhook).
