# Allowed APIs — Reference Doc (Phase 0)

Source-of-truth signatures for the Amanda agent. **Do NOT invent APIs.** If unsure, mark as UNVERIFIED and smoke-test before coding.

**Changelog — 2026-05-28 introspection finalized:**
- All 5 previously-unverified Agno items now CONFIRMED via live `inspect.signature` on agno 2.6.9 (see §1.4–§1.8). `openai`, `sqlalchemy`, `psycopg` installed into `.venv` to allow the symbols to import.
- `OpenAIChat.__init__` full param list captured (52 kwargs).
- `PostgresDb` vs `AsyncPostgresDb` constructors captured; both exist in `agno.db.postgres`. `arun` does NOT require `AsyncPostgresDb` (Agno wraps sync `PostgresDb` in a thread executor) — but for true async I/O under FastAPI use `AsyncPostgresDb` with `postgresql+psycopg` URL (the async variant uses the same URL scheme — it manages its own async engine).
- `output_schema=PydanticModel` works on `OpenAIChat` directly: `supports_native_structured_outputs=True` by default; the model translates the Pydantic class into `response_format={"type":"json_schema","json_schema":{"name":..., "schema":..., "strict":True}}`. No need to swap to `OpenAIResponses`.
- `@tool` decorator lives at `agno.tools.decorator` (re-exported as `agno.tools.tool`). Accepts 20 kwargs (see §1.5). Async tools supported natively.
- `session_state` accessed inside tools via `RunContext` dataclass (`agno.run.RunContext`) — injected by name when the tool signature declares a `run_context: RunContext` param. Fields confirmed: `run_id, session_id, user_id, session_state: Dict[str,Any], dependencies, metadata, messages, …`.
- `Agent.arun` signature locked (22 params).

**Earlier changelog — Confirmed via user-provided links 2026-05-28:**
- Agno installed locally: **2.6.9** (venv at `/Users/raulbehnke/zaf-autovip/.venv`).
- Agno `Agent.__init__` introspected: confirmed `db=`, `output_schema=`, `add_history_to_context=`, `num_history_runs=`. Confirmed `storage=`, `response_model=`, `add_history_to_messages=`, `messages=` do NOT exist as kwargs.
- `Agent.run()` / `Agent.arun()` signatures locked via `inspect.signature` — they take `input` (str | list | dict | Message | BaseModel | list[Message]) plus per-run overrides. No `messages=` kwarg.
- GHL `POST /conversations/messages` body schema (`SendMessageBodyDto`) verified: type enum is `SMS | RCS | Email | WhatsApp | IG | FB | Custom | Live_Chat | TIKTOK`. **No `userId` field. No InternalComment type.**
- GHL `DELETE /contacts/{contactId}/tags` confirmed (Version `2021-07-28`, body `{"tags":[...]}`).
- GHL `GET /users/search` discovered (Version `2021-07-28`, required `companyId`).
- No internal-comment / note endpoint exists under `/conversations/*`. Use `POST /contacts/{id}/notes` for contact-level notes; `POST /conversations/messages/inbound` for synthetic inbound messages.

- Agno version: **2.6.9** (installed in `/Users/raulbehnke/zaf-autovip/.venv`).
- GHL specs pulled from official repo: `https://github.com/GoHighLevel/highlevel-api-docs` (apps/*.json — OpenAPI 3).
- OpenAI spec pulled from `https://github.com/openai/openai-openapi/raw/master/openapi.yaml`.

---

## 1. Agno Framework

> Agno **2.6.9** installed at `/Users/raulbehnke/zaf-autovip/.venv`. Signatures below confirmed via `inspect.signature(Agent.__init__)` (115 kwargs total) and live doc pages.

### 1.1 `Agent(...)` constructor — confirmed

Confirmed via local `inspect.signature(Agent.__init__)` on agno 2.6.9 + docs at `/agents/usage/agent-with-storage` and `/database/providers/postgres/usage/postgres-for-agent`:

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat  # see 1.4
from agno.db.postgres import PostgresDb     # see 1.2

agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    db=PostgresDb(db_url="postgresql+psycopg://ai:ai@localhost:5532/ai"),
    tools=[...],                  # list of @tool functions or Toolkit instances
    instructions="...",           # str or list[str]
    output_schema=MyPydanticModel,  # confirmed kwarg name
    add_history_to_context=True,    # confirmed kwarg name
    num_history_runs=5,             # confirmed kwarg name
    markdown=True,
)
```

**Important naming changes (vs older Agno tutorials):**
- `storage=` → `db=`
- `response_model=` → `output_schema=`
- `add_history_to_messages=` → `add_history_to_context=`
- `PostgresStorage` → `PostgresDb` (and `AsyncPostgresDb`)

Doc: <https://docs.agno.com/agents/building-agents.md>, <https://docs.agno.com/agents/usage/agent-with-structured-output.md>

### 1.2 `PostgresDb` / `AsyncPostgresDb` storage — CONFIRMED

Both classes live in `agno.db.postgres` (`from agno.db.postgres import PostgresDb, AsyncPostgresDb`). Constructors verified via `inspect.signature` on 2.6.9:

```python
PostgresDb(
    db_url: str | None = None,
    db_engine: Engine | None = None,           # pre-built SQLAlchemy engine (alternative to db_url)
    db_schema: str | None = None,              # Postgres schema (default "ai" per agno conventions)
    session_table: str | None = None,
    culture_table: str | None = None,
    memory_table: str | None = None,
    metrics_table: str | None = None,
    eval_table: str | None = None,
    knowledge_table: str | None = None,
    traces_table: str | None = None,
    spans_table: str | None = None,
    versions_table: str | None = None,
    components_table: str | None = None,
    component_configs_table: str | None = None,
    component_links_table: str | None = None,
    learnings_table: str | None = None,
    schedules_table: str | None = None,
    schedule_runs_table: str | None = None,
    approvals_table: str | None = None,
    id: str | None = None,
    create_schema: bool = True,
)

AsyncPostgresDb(
    # Same kwargs as PostgresDb EXCEPT it lacks: components_table, component_configs_table, component_links_table.
    # All other kwargs identical (db_url, db_engine, db_schema, *_table, id, create_schema).
)
```

```python
from agno.db.postgres import PostgresDb, AsyncPostgresDb

# Sync (used by Agent.run + Agent.arun-via-thread-executor):
db = PostgresDb(db_url="postgresql+psycopg://ai:ai@localhost:5432/ai")

# True async (recommended under FastAPI; AsyncPostgresDb builds its own async engine internally):
adb = AsyncPostgresDb(db_url="postgresql+psycopg://ai:ai@localhost:5432/ai")
```

**`arun` does NOT REQUIRE `AsyncPostgresDb`.** A `PostgresDb` works with `Agent.arun(...)` (Agno offloads sync DB calls to a thread). For high-throughput FastAPI use `AsyncPostgresDb` to avoid the executor hop.

Doc: <https://docs.agno.com/database/providers/postgres/overview.md>, <https://docs.agno.com/database/providers/async-postgres/overview.md>

### 1.3 `run()` / `arun()` execution — confirmed via introspection

Full sync signature (agno 2.6.9):
```
Agent.run(self, input, *, stream=None, stream_events=None, user_id=None,
          session_id=None, session_state=None, run_context=None, run_id=None,
          audio=None, images=None, videos=None, files=None,
          knowledge_filters=None, add_history_to_context=None,
          add_dependencies_to_context=None, add_session_state_to_context=None,
          dependencies=None, metadata=None, output_schema=None,
          yield_run_output=None, debug_mode=None, **kwargs)
```
`arun` full signature (CONFIRMED — `inspect.signature(Agent.arun)` on 2.6.9, 22 params):
```python
Agent.arun(
    self,
    input: str | list | dict | Message | BaseModel | list[Message],   # required
    *,
    stream: bool | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    session_state: dict[str, Any] | None = None,
    run_context: RunContext | None = None,
    run_id: str | None = None,
    audio: Sequence[Audio] | None = None,
    images: Sequence[Image] | None = None,
    videos: Sequence[Video] | None = None,
    files: Sequence[File] | None = None,
    stream_events: bool | None = None,
    knowledge_filters: dict | list[FilterExpr] | None = None,
    add_history_to_context: bool | None = None,
    add_dependencies_to_context: bool | None = None,
    add_session_state_to_context: bool | None = None,
    dependencies: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    output_schema: type[BaseModel] | dict | None = None,
    yield_run_output: bool | None = None,
    debug_mode: bool | None = None,
    background: bool = False,
    **kwargs,
) -> RunOutput  # or AsyncIterator[RunOutputEvent] if stream=True
```

```python
response: RunOutput = agent.run("user text", session_id="...", user_id="...")
# Pass prior history as a list of dict/Message — NOT via messages= (no such kwarg).
response = agent.run(
    [{"role": "user", "content": "..."},
     {"role": "assistant", "content": "..."},
     {"role": "user", "content": "new turn"}],
    session_id="...",
)
```

- `stream=True` → returns `Iterator[RunOutputEvent]` (or `AsyncIterator` for `arun`).
- Access typed structured output via `response.content` (instance of `output_schema`).
- **`messages=` kwarg does NOT exist.** Use `input=` as a list of messages, or rely on `db=` + `session_id` for automatic history rehydration.

Doc: <https://docs.agno.com/agents/running-agents.md>

### 1.4 `OpenAIChat` model — CONFIRMED (full 52-param signature)

`inspect.signature(OpenAIChat.__init__)` on agno 2.6.9 yielded:

```python
OpenAIChat(
    # --- identity ---
    id: str = "gpt-5.4-mini",          # NOTE: default in 2.6.9 — override for prod ("gpt-4o-mini", etc.)
    name: str = "OpenAIChat",
    provider: str = "OpenAI",
    model_type: ModelType = ModelType.MODEL,

    # --- structured outputs (used by Agent.output_schema=) ---
    supports_native_structured_outputs: bool = True,   # OpenAIChat uses json_schema strict mode
    supports_json_schema_outputs: bool = False,
    strict_output: bool = True,

    # --- system / instructions hooks ---
    _tool_choice: str | dict | None = None,
    system_prompt: str | None = None,
    instructions: str | list[str] | None = None,
    tool_message_role: str = "tool",
    assistant_message_role: str = "assistant",

    # --- caching ---
    cache_response: bool = False,
    cache_ttl: int | None = None,
    cache_dir: str | None = None,

    # --- retries ---
    retries: int = 0,
    delay_between_retries: int = 1,
    exponential_backoff: bool = False,
    retry_with_guidance: bool = True,
    retry_with_guidance_limit: int = 1,

    # --- metrics ---
    collect_metrics_on_completion: bool = False,

    # --- OpenAI Chat Completions params (forwarded directly) ---
    store: bool | None = None,
    reasoning_effort: str | None = None,        # "low" | "medium" | "high"
    verbosity: str | None = None,
    metadata: dict | None = None,
    frequency_penalty: float | None = None,
    logit_bias: dict | None = None,
    logprobs: bool | None = None,
    top_logprobs: int | None = None,
    max_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    modalities: list[str] | None = None,
    audio: dict | None = None,
    presence_penalty: float | None = None,
    seed: int | None = None,
    stop: str | list[str] | None = None,
    temperature: float | None = None,
    user: str | None = None,
    top_p: float | None = None,
    service_tier: str | None = None,

    # --- HTTP escape hatches ---
    extra_headers: dict | None = None,
    extra_query: dict | None = None,
    extra_body: dict | None = None,
    request_params: dict | None = None,
    role_map: dict | None = None,

    # --- client config ---
    api_key: str | None = None,                 # falls back to OPENAI_API_KEY env
    organization: str | None = None,
    base_url: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    default_headers: dict | None = None,
    default_query: dict | None = None,
    http_client: httpx.Client | None = None,
    client_params: dict | None = None,
    client: OpenAI | None = None,
    async_client: AsyncOpenAI | None = None,
)
```

```python
from agno.models.openai import OpenAIChat
model = OpenAIChat(
    id="gpt-4o-mini",
    api_key=OPENAI_KEY,
    temperature=0.2,
    max_completion_tokens=2000,
    timeout=30.0,
)
```

**`output_schema=PydanticModel` works with `OpenAIChat` directly** (CONFIRMED via source — see `_format_messages_and_response_format`): the model serializes the Pydantic class into a `json_schema` strict response_format. No need to swap to `OpenAIResponses`.

### 1.5 Tools — `@tool` + session_state access — CONFIRMED

`from agno.tools import tool` (re-exported from `agno.tools.decorator`). Signature: `tool(*args, **kwargs)`. Valid kwargs (frozen set in source):

```
name, description, strict, instructions, add_instructions,
show_result, stop_after_tool_call,
requires_confirmation, requires_user_input, user_input_fields,
external_execution, external_execution_silent,
pre_hook, post_hook, tool_hooks,
cache_results, cache_dir, cache_ttl
```

Async tools are **explicitly supported** (the decorator docstring shows `@tool / async def my_async_function(): ...`).

**`RunContext` (CONFIRMED — dataclass at `agno.run.RunContext`):**

```python
RunContext(
    run_id: str,                                   # required
    session_id: str,                               # required
    user_id: str | None = None,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    dependencies: dict[str, Any] | None = None,
    knowledge_filters: dict | list[FilterExpr] | None = None,
    metadata: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,   # <-- read/write here from inside tool
    output_schema: type[BaseModel] | dict | None = None,
    messages: list[Message] | None = None,
    tools: list[Any] | None = None,
    knowledge: Any | None = None,
    members: list[Any] | None = None,
)
```

**Reading/writing `session_state` from inside a tool** — declare a `run_context: RunContext` param; Agno injects it by name:

```python
from agno.tools import tool
from agno.run import RunContext

@tool
def remember_lead_stage(run_context: RunContext, stage: str) -> str:
    """Persist current lead stage into the agent session_state."""
    if run_context.session_state is None:
        run_context.session_state = {}
    run_context.session_state["lead_stage"] = stage
    return f"stage={stage}"

@tool(name="ghl_send_sms", show_result=False)
async def ghl_send_sms(run_context: RunContext, contact_id: str, message: str) -> dict:
    """Send an SMS via GHL and record the outbound id into session_state."""
    # ... async httpx call ...
    out_id = "msg_abc"
    state = run_context.session_state or {}
    state.setdefault("outbound_ids", []).append(out_id)
    run_context.session_state = state
    return {"messageId": out_id}
```

- Mutations to `run_context.session_state` are persisted via the attached `db=` at end of run (same `session_id`).
- Other injectable param names by convention: `agent`, `team`, `images`, `videos`, `audio`, `files` (declared on the function signature; Agno fills them at call-time).
- Toolkits: `from agno.tools.<name> import <Name>Tools` — instantiate and pass instances in `tools=[...]`.

Doc: <https://docs.agno.com/agents/usage/agent-with-tools.md>

### 1.6 Sessions / state

- `session_id` groups runs into a thread; persisted automatically when `db=` is set.
- `agent.get_session(session_id="...")` → returns object with `.runs`, `.created_at`, `.updated_at`.
- `session_state` lives on `RunContext` inside tools; writes persist at end of run via attached `db`.

Doc: <https://docs.agno.com/database/session-storage.md>

### 1.7 Passing external chat history — CONFIRMED

`messages=` kwarg does NOT exist on `run()`/`arun()` (verified via introspection on 2.6.9). Two supported patterns:

```python
# Pattern A — pack prior turns into input as a list of dicts:
prior = [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "new question"},
]
response = agent.run(prior, session_id=sid)

# Pattern B — rely on Agno session storage:
# Configure Agent(db=PostgresDb(...), add_history_to_context=True, num_history_runs=N)
# then just call agent.run("new question", session_id=sid) — prior turns auto-loaded.
```

---

## 2. GoHighLevel API v2

**Base URL:** `https://services.leadconnectorhq.com`
**Auth:** `Authorization: Bearer <PIT or OAuth token>`
**Accept:** `application/json`
**Version header is REQUIRED per endpoint — value differs.**

Source: <https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps>

### 2.1 Conversations

#### `GET /conversations/search` — `Version: 2021-04-15`

Query params (locationId required):

| Param | Type | Notes |
|---|---|---|
| `locationId` | str | **required** |
| `contactId` | str | filter by contact |
| `assignedTo`, `followers`, `mentions` | csv str | user IDs |
| `query` | str | text search |
| `sort` | `asc`\|`desc` | |
| `sortBy` | `last_message_date`\|`last_manual_message_date`\|... | |
| `limit` | num | |
| `status` | `all`\|`read`\|`unread`\|`starred`\|`recents` | |
| `startDate`/`endDate` | num (epoch ms) | |
| `lastMessageType` | enum (`TYPE_SMS`, `TYPE_INTERNAL_COMMENT`, ...) | |
| `lastMessageDirection` | `inbound`\|`outbound` | |

Response: `{ "conversations": [{ id, contactId, locationId, lastMessageBody, lastMessageType, type, unreadCount, fullName, email, phone, ... }] }`

```python
async with httpx.AsyncClient(base_url="https://services.leadconnectorhq.com") as c:
    r = await c.get(
        "/conversations/search",
        headers={"Authorization": f"Bearer {PIT}", "Version": "2021-04-15", "Accept": "application/json"},
        params={"locationId": LOC, "contactId": CID, "limit": 1, "sortBy": "last_message_date"},
    )
```

#### `GET /conversations/{conversationId}/messages` — `Version: 2021-04-15`

Query: `lastMessageId` (cursor), `limit` (default ~20, server caps), `type` (filter).

Response: `{ lastMessageId, nextPage: bool, messages: [{ id, type (num), messageType (enum), locationId, contactId, conversationId, dateAdded (ISO), body, direction (inbound|outbound), status, contentType, attachments: [url,...] }] }`

```python
r = await c.get(
    f"/conversations/{conv_id}/messages",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-04-15"},
    params={"limit": 50},
)
```

#### `POST /conversations/messages` — `Version: 2021-04-15` — Send message

Body schema `SendMessageBodyDto`. **Required (per spec): `type`, `subType`, `contactId`, `status`.** Full field list verified from OpenAPI:

| Field | Type | Notes |
|---|---|---|
| `type` | enum (req) | `SMS \| RCS \| Email \| WhatsApp \| IG \| FB \| Custom \| Live_Chat \| TIKTOK` |
| `subType` | object (req per spec) | Message subtype |
| `contactId` | str (req) | |
| `status` | enum (req) | `delivered \| failed \| pending \| read` |
| `message` | str | Text body |
| `html`, `subject`, `emailFrom`, `emailTo`, `emailCc`, `emailBcc`, `emailReplyMode`, `replyMessageId`, `threadId`, `templateId`, `customSubtypeId` | — | Email-specific |
| `fromNumber`, `toNumber` | str | SMS-specific |
| `attachments` | array<url> | |
| `appointmentId` | str | |
| `scheduledTimestamp` | num (UTC seconds) | |
| `conversationProviderId` | str | |
| `usesNativeSchedulingAi`, `optimizationPeriod` | — | AI scheduling |
| `forward` | object | Email forwarding config |

⚠️ **`InternalComment` is NOT in the `type` enum.** **No `userId` field exists on this endpoint** — SMS attribution to a specific user is not supported via this API. There is **no documented send-internal-comment endpoint anywhere in `/conversations/*`** (full path list checked: search, get/update/delete conversation, custom-subtypes, unsubscriptions, messages export/get/inbound/outbound/review-reply/upload/status/attachments/recording/transcription, live-chat typing, create conversation — none for internal comments).

```python
r = await c.post(
    "/conversations/messages",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-04-15", "Content-Type": "application/json"},
    json={"type": "SMS", "contactId": cid, "message": "Olá!"},  # subType/status defaulted server-side in practice
)
```

#### `POST /conversations/messages/inbound` — `Version: 2021-04-15` — Synthetic inbound message

Body `ProcessMessageBodyDto`. **Required:** `type`, `conversationId`, `contactId`, `conversationProviderId`. Useful for injecting transcribed audio as inbound text. `type` enum here is wider: includes `Call`, `IVR_Call`, `Campaign_Call`, `Campaign_VoiceMail`, `WebChat`, `FORM_SUBMISSION`, `ALL_IN_ONE_CHAT`, plus all outbound types.

### 2.2 Contacts — Tags & Notes

#### `POST /contacts/{contactId}/tags` — `Version: 2021-07-28` — Add tags
Body: `{"tags": ["tag1", "tag2"]}` (required).

#### `DELETE /contacts/{contactId}/tags` — `Version: 2021-07-28` — Remove tags
Body: `{"tags": ["tag1"]}` (required).

✅ **Confirmed: use `DELETE` with JSON body.** There is **no** `POST /contacts/{id}/tags/remove` endpoint in the spec.

```python
# Remove tag
r = await c.request(
    "DELETE",
    f"/contacts/{cid}/tags",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-07-28", "Content-Type": "application/json"},
    json={"tags": ["aguardando-resposta"]},
)
```

#### `POST /contacts/{contactId}/notes` — `Version: 2021-07-28`
Body `NotesDTO`: `{ "body": "text", "userId": "...", "title": "...", "color": "#FFAA00", "pinned": false }` — only `body` required.

```python
r = await c.post(
    f"/contacts/{cid}/notes",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-07-28"},
    json={"body": "Resumo do turno: ..."},
)
```

### 2.3 Calendars

#### `GET /calendars/{calendarId}/free-slots` — `Version: 2021-04-15`
Query: `startDate` (epoch ms, **required**), `endDate` (epoch ms, **required**), `timezone` (e.g. `America/Sao_Paulo`), `userId`, `userIds[]`.

Response shape (additionalProperties keyed by date):
```json
{ "2024-10-28": { "slots": ["2024-10-28T10:00:00-05:00", ...] }, "2024-10-29": {...} }
```

```python
r = await c.get(
    f"/calendars/{cal_id}/free-slots",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-04-15"},
    params={"startDate": start_ms, "endDate": end_ms, "timezone": "America/Sao_Paulo"},
)
```

#### `POST /calendars/events/appointments` — `Version: 2021-04-15`
Body `AppointmentCreateSchema`. **Required:** `calendarId`, `locationId`, `contactId`, `startTime` (ISO with offset, e.g. `2021-06-23T03:30:00+05:30`). Optional: `endTime`, `title`, `appointmentStatus` (`new|confirmed|cancelled|showed|noshow|invalid`), `assignedUserId`, `description`, `address`, `meetingLocationType` (`custom|zoom|gmeet|phone|address|ms_teams|google`), `toNotify`, `ignoreDateRange`, `ignoreFreeSlotValidation`, `rrule`.

```python
r = await c.post(
    "/calendars/events/appointments",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-04-15"},
    json={
        "calendarId": cal,
        "locationId": loc,
        "contactId": cid,
        "startTime": "2026-06-23T10:00:00-03:00",
        "endTime":   "2026-06-23T10:30:00-03:00",
        "title": "Auto Vip - test drive",
        "appointmentStatus": "confirmed",
    },
)
```

### 2.4 Users

#### `GET /users/search` — `Version: 2021-07-28`

Query params:

| Param | Type | Notes |
|---|---|---|
| `companyId` | str | **required** |
| `query` | str | text search (name/email) |
| `locationId` | str | scope to a sub-account |
| `type` | str | user type filter |
| `role` | str | role filter |
| `ids` | csv str | filter to specific user IDs |
| `skip` | str (num) | default `0` |
| `limit` | str (num) | default `25` |
| `sort`, `sortDirection` | str | |
| `enabled2waySync` | bool | |

```python
r = await c.get(
    "/users/search",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-07-28"},
    params={"companyId": COMP, "query": "raul", "locationId": LOC, "limit": 10},
)
```

Companion: `POST /users/search/filter-by-email` (same Version) for bulk email lookups.

Use this to resolve `@username` mentions in conversation bodies (`<userId>...</userId>` HTML tags) back to display names if needed.

### 2.5 Locations — Custom Values

#### `GET /locations/{locationId}/customValues/{id}` — `Version: 2021-07-28`
Response:
```json
{ "customValue": { "id": "...", "name": "...", "fieldKey": "{{ custom_values.foo }}", "value": "...", "locationId": "..." } }
```

```python
r = await c.get(
    f"/locations/{loc}/customValues/{cv_id}",
    headers={"Authorization": f"Bearer {PIT}", "Version": "2021-07-28"},
)
val = r.json()["customValue"]["value"]
```

---

## 3. OpenAI

### 3.1 `POST /v1/audio/transcriptions` — multipart

Endpoint: `https://api.openai.com/v1/audio/transcriptions`
Headers: `Authorization: Bearer <key>`, `Content-Type: multipart/form-data` (let httpx set boundary).
Form fields:

| Field | Type | Notes |
|---|---|---|
| `file` | binary | **required** — flac/mp3/mp4/mpeg/mpga/m4a/ogg/wav/webm |
| `model` | str | **required** — `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, ... |
| `language` | str | ISO-639-1 (e.g. `pt`) — improves accuracy/latency |
| `prompt` | str | optional style hint (not supported on `gpt-4o-transcribe-diarize`) |
| `response_format` | str | `json` (default), `text`, `srt`, `vtt`, `verbose_json`, `diarized_json` |
| `temperature` | num | 0..1 |

```python
async with httpx.AsyncClient() as c:
    files = {"file": ("audio.mp3", audio_bytes, "audio/mpeg")}
    data = {"model": "whisper-1", "language": "pt"}
    r = await c.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}"},
        files=files, data=data,
    )
text = r.json()["text"]
```

Doc: <https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.yaml> (path `/audio/transcriptions`).

### 3.2 Chat — structured output via `response_format: json_schema`

For `gpt-4o-mini` chat completions:

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "amanda_decision",     # required, a-zA-Z0-9_-, max 64 chars
        "description": "...",          # optional
        "schema": { ...JSON Schema... }, # required
        "strict": True                  # recommended
    }
}
```

`name` is required inside `json_schema`. With `strict=True`, the schema must use only the supported JSON-Schema subset (no `pattern`, all properties required and listed in `required`, `additionalProperties: false`, etc).

Prefer using Agno's `output_schema=PydanticModel` which wraps this automatically.

Doc: spec component `ResponseFormatJsonSchema` in openai-openapi.yaml.

---

## 4. Anti-patterns / things that DO NOT exist

| Wrong | Correct |
|---|---|
| `from agno.storage.postgres import PostgresStorage` | `from agno.db.postgres import PostgresDb` (or `AsyncPostgresDb`) |
| `Agent(storage=...)` | `Agent(db=...)` |
| `Agent(response_model=Foo)` | `Agent(output_schema=Foo)` |
| `Agent(add_history_to_messages=True)` | `Agent(add_history_to_context=True)` |
| `POST /contacts/{id}/tags/remove` | **Does not exist.** Use `DELETE /contacts/{id}/tags` with JSON body `{"tags":[...]}` |
| `POST /conversations/messages` with `"type": "InternalComment"` | **Not in the public spec.** Allowed `type` enum: `SMS, RCS, Email, WhatsApp, IG, FB, Custom, Live_Chat, TIKTOK`. No endpoint exists for internal comments anywhere under `/conversations/*` (full path list audited). Use `POST /contacts/{id}/notes` for contact-scoped notes instead. |
| Sending SMS with `"userId": "..."` for attribution | **Not a field on `SendMessageBodyDto`.** SMS API attributes the message to the PIT/OAuth token owner; per-message user attribution is not supported. |
| `Agent.run(prompt, messages=[...])` | **`messages=` is not a kwarg** (verified on 2.6.9). Pack history into `input=[...]` or use `db=` + `session_id` + `add_history_to_context=True`. |
| Hard-coding `Version: 2021-07-28` for all GHL calls | Conversations/Calendars use `2021-04-15`; Contacts/Locations use `2021-07-28`. Pin per-call. |
| `gpt-4o-mini` audio transcription | Whisper endpoint takes `whisper-1` or `gpt-4o-*-transcribe`; `gpt-4o-mini` is chat-only. |
| Calling `Agent.run` with `messages=[...]` and assuming it works | **Confirmed broken** — `messages=` is not in the signature. Use `input=[...]` or session-history rehydration (§1.7). |

---

## 5. Unverified / needs smoke test

1. **Agno** — ✅ ALL CONFIRMED (2026-05-28 introspection finalized).
   - `OpenAIChat(...)` full param list locked (52 kwargs — see §1.4).
   - `PostgresDb` works under `arun` via thread executor; `AsyncPostgresDb` is the preferred native-async variant (see §1.2).
   - `output_schema=PydanticModel` works directly on `OpenAIChat` (`supports_native_structured_outputs=True`, json_schema strict mode — see §1.4).
   - `@tool` decorator + `RunContext.session_state` access pattern confirmed (see §1.5).
   - `Agent.arun(...)` full 22-param signature locked (see §1.3).

2. **GHL — needs PIT smoke test**:
   - `GET /conversations/search` with `contactId` + `locationId` → confirm latest conversation returned first.
   - `GET /conversations/{id}/messages` → confirm `direction`/`messageType` fields, attachment URL behaviour for audio (`TYPE_SMS` with audio attachment vs voicemail).
   - `POST /conversations/messages` SMS — confirm minimum body (spec says `subType`+`status` required, but most clients send only `type`+`contactId`+`message`; defaults likely applied server-side).
   - **InternalComment workflow**: confirmed NO endpoint. Confirm with GHL support whether internal comments are UI-only or require a private/undocumented endpoint. Until confirmed, route "internal" content into a contact note via `POST /contacts/{id}/notes`.
   - `DELETE /contacts/{id}/tags` with body — confirm httpx sends DELETE body (some HTTP clients strip it; httpx does not by default but verify).
   - `GET /locations/{loc}/customValues/{id}` — confirm PIT scope includes Custom Values read.
   - `GET /calendars/{cal}/free-slots` — confirm timezone string format accepted (IANA name) and whether response keys are local-date or UTC.
   - `GET /users/search` — confirm PIT scope includes `users.readonly` and `companyId` is discoverable from the PIT context.

3. **OpenAI**:
   - Confirm `whisper-1` accepts `language="pt"` (per spec, ISO-639-1).
   - Confirm `gpt-4o-mini` honors `response_format: json_schema` with `strict: true` (it does per release notes — sanity check on first call).

---

## 6. Quick reference — Version header matrix

| API group | Version |
|---|---|
| Conversations (search, messages, send) | `2021-04-15` |
| Calendars (free-slots, appointments) | `2021-04-15` |
| Contacts (tags, notes, get/update) | `2021-07-28` |
| Locations / Custom Values | `2021-07-28` |
| Users (search, get, update) | `2021-07-28` |
