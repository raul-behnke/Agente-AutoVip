# Correções pós-Phase 0 (2026-05-28)

Aplicar estas correções ao implementar. `specs.md` e `plan.md` ficam históricos; código segue daqui.

## Agno (v2.6.9)

| Antigo (specs/plan) | Correto (verificado) |
|---|---|
| `PostgresStorage` | `PostgresDb` (`from agno.db.postgres import PostgresDb`) |
| `storage=` | `db=` |
| `response_model=` | `output_schema=` |
| `add_history_to_messages=False` | `add_history_to_context=False` |
| `agent.arun(message=..., messages=[...])` | `agent.arun(input=..., session_id=...)` — não existe `messages=` kwarg |
| `table_name="agno_sessions"` | `PostgresDb(db_url=..., session_table="agno_sessions")` (confirmar nome exato do kwarg via introspecção) |

- **Tools:** `from agno.tools import tool` (decorator). Tools async OK.
- **session_state em tool:** declarar param `run_context: RunContext` (de `agno.run.RunContext`); ler/escrever via `run_context.session_state`. Persistência automática se `db=` configurado.
- **OpenAIChat:** default model = `gpt-5.4-mini` — sobrescrever com `id="gpt-4o-mini"`.
- **`output_schema=PydanticModel`** funciona com `OpenAIChat` (gera `response_format json_schema strict`).
- **DB URL:** usar `postgresql+psycopg://` (psycopg3), não `asyncpg`. `PostgresDb` sync OK com `arun` (Agno roda em thread executor).

## GHL

### InternalComment NÃO existe

`POST /conversations/messages` aceita apenas: `SMS | RCS | Email | WhatsApp | IG | FB | Custom | Live_Chat | TIKTOK`. Nenhum endpoint `/conversations/*` cria comentário interno.

**Substituição:** usar `POST /contacts/{contactId}/notes` com body `body: "@<nome> <texto-handoff> userId:<id>"` (texto plano, sem renderização de mention).

→ Função `add_internal_comment(...)` vira `add_handoff_note(contact_id, summary, mentioned_user_id)`.

### SMS sem `userId` no body

`SendMessageBodyDto` não aceita `userId`. Atribuição vem do **PIT owner** (Suporte Integrações = `AI6WhiMbluBEOX1vI1ID` é o dono do token).

→ Remover `userId=SENDER_USER_ID` da chamada `send_sms`.

### Remove tag

Confirmado: `DELETE /contacts/{contactId}/tags`, Version `2021-07-28`, body `{"tags":["agent-ia"]}`. Não usar `POST /tags/remove`.

### Headers Version (por endpoint)

- Conversations + Calendars: `Version: 2021-04-15`
- Contacts + Locations + Users: `Version: 2021-07-28`

### Áudio transcrito (sintético)

Não publicar transcrição como mensagem na conversa. Mantém só no `turn_input` interno do agente (sem reenviar pro GHL).

## Driver Postgres

Trocar `asyncpg` por `psycopg[binary]` (Agno usa SQLAlchemy + psycopg3). Manter `asyncpg` só se houver outro uso direto — provavelmente remover.

## Schema response Amanda

Mantido: `class AmandaResponse(BaseModel): messages: list[str]`. Funciona via `output_schema=`.
