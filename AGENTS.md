# Sleep Calendar Agent

A sleep-focused calendar scheduling agent backed by a mock calendar HTTP API.
The agent uses an LLM (via OpenRouter) with native tool calling to read and
manage calendar events, always treating the user's sleep block as inviolable.

Built with FastAPI, SQLite (via SQLModel), New York local datetimes, UUID
identifiers, and the OpenAI-compatible OpenRouter API.

## Project structure

```
agent/
  main.py          # REPL entry point  (uv run python agent/main.py)
  tools.py         # OpenAI tool schemas + HTTP dispatcher for every API endpoint
  system_prompt.py # Lazily-built system prompt (injects tool list + current time)
mock_calendar_api/ # FastAPI + SQLModel mock calendar HTTP API
tests/             # API endpoint unit tests (pytest, in-memory SQLite)
evals/             # Agent evaluation suite (4 layers — see Evals below)
user-prefs.json    # User sleep preferences (bedtime, waketime, wind_down_mins)
.env               # OPENROUTER_API_KEY and CALENDAR_API_URL
Dockerfile         # Multi-stage Docker build for the calendar API
docker-compose.yml # Compose file to run the API with persistent SQLite volume
.dockerignore      # Keeps images lean (excludes tests, evals, agent, etc.)
Makefile           # Shortcuts for every common workflow (run `make help`)
README.md          # User-facing setup and usage guide
```

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/) | Docker ≥ 20, Compose v2 | Run the mock calendar API |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | ≥ 0.9 | Python package/project manager (agent & tests) |
| Python | ≥ 3.13 | Required by the project; uv installs it automatically if missing |

An [OpenRouter](https://openrouter.ai) API key is needed to run the agent and
the live-LLM evaluation layers.

## Quickstart

**1. Configure**

Create a `.env` file:
```
OPENROUTER_API_KEY=sk-or-...
CALENDAR_API_URL=http://127.0.0.1:8000   # default
```

Optionally edit sleep preferences in `user-prefs.json`:
```json
{
  "bedtime": "12:30 AM",
  "waketime": "8:15 AM",
  "wind_down_mins": 90
}
```

**2. Start the calendar API (Docker)**

```bash
make docker-up          # or: docker compose up -d
```

The API serves on `http://127.0.0.1:8000` with Swagger docs at
`http://127.0.0.1:8000/docs`. The SQLite database is persisted in a Docker
volume (`calendar-data`) so data survives container restarts.

The database path is configurable via the `DATABASE_URL` environment variable
(defaults to `sqlite:///./calendar.db` when running outside Docker).

Other Docker targets:

```bash
make docker-logs        # tail container logs
make docker-down        # stop the container
make docker-reset       # stop and delete the database volume
```

You can also run the API directly without Docker:

```bash
make api                # or: uv run python main.py
```

**3. Start the agent**

```bash
make agent              # or: uv run python agent/main.py
```

The agent reads sleep preferences from `user-prefs.json`, injects the current
New York time into the system prompt, then opens a terminal REPL. Type any
scheduling request in plain English; the agent calls calendar tools as needed
and confirms changes in plain language. Type `exit`, `quit`, or `bye` (or
`Ctrl-C` / `Ctrl-D`) to quit.

## Data model

Every event has:

| field         | type              | notes                                                  |
|---------------|-------------------|--------------------------------------------------------|
| `id`          | UUID              | server-generated; may be supplied on create for upsert  |
| `title`       | string            | required, 1–255 chars                                   |
| `start`       | datetime (NY)     | required, stored naive NY local, returned zone-aware   |
| `end`         | datetime (NY)     | required, must be after `start`                         |
| `description` | string?           | optional, ≤4096 chars                                   |
| `location`    | string?           | optional, ≤255 chars                                    |
| `metadata_`   | object?           | free-form JSON (e.g. sleep quality, type, source)       |
| `created_at`  | datetime (NY)     | auto                                                   |
| `updated_at`  | datetime (NY)     | auto, bumped on update                                  |

### Timezone

All datetimes are in **New York local time** (`America/New_York`), which
observes DST: EST (UTC-05:00) in winter, EDT (UTC-04:00) in summer. Inputs may
be naive (assumed New York local) or carry an offset (converted to New York).
Stored values are naive New York wall-clock; responses re-attach the zone so
the offset reflects the actual DST in effect at that moment.

## Endpoints

### Create event
`POST /events` → `201 EventRead`

```json
{ "title": "Sleep (night)", "start": "2026-06-29T22:00:00", "end": "2026-06-30T07:00:00", "metadata_": {"quality": 0.82} }
```

### Get event by ID
`GET /events/{id}` → `200 EventRead` (404 if missing)

### List / range query
`GET /events?start=...&end=...` → `200 [EventRead]`

Returns events that **overlap** `[start, end)` (i.e. `event.start < end` and
`event.end > start`). Omit both params to list everything. Requires `start < end`.

### Update event
`PATCH /events/{id}` → `200 EventRead`

Partial update; only supplied fields are written. `start`/`end` are
re-validated to ensure `end > start`.

```json
{ "title": "Sleep (moved)", "end": "2026-06-30T08:00:00" }
```

### Delete event
`DELETE /events/{id}` → `204 No Content` (404 if missing)

### Batch create / update (upsert)
`POST /events/batch` → `200 [EventRead]`

Body is a JSON array of create payloads. Each item **with** an `id` updates the
matching event if it exists, otherwise creates it with that ID; items without an
`id` create new events. All items are applied in one transaction.

### Clear all (reset to empty)
`DELETE /events` → `200 {"deleted": <count>}`

### Seed deterministic data
`POST /seed?replace=true` → `200 [EventRead]`

Inserts a fixed sleep-themed dataset anchored to today. With `replace=true`
(default) the table is cleared first, yielding a known starting state for tests.

## Agent details

### LLM
Model: `google/gemini-2.5-flash` via [OpenRouter](https://openrouter.ai) using
the OpenAI-compatible API (`https://openrouter.ai/api/v1`). Non-streaming,
in-memory conversation history for the duration of a single run.

### Tool calling
The agent uses native OpenAI-style function/tool calling. `agent/tools.py`
defines one tool per API endpoint with JSON schemas that exactly match the
API's request shapes, and a `dispatch()` function that executes the
corresponding `httpx` call. Tool invocations are printed to the terminal
as `[tool]` / `[tool result]` lines so you can follow along.

The `seed_calendar` endpoint (`POST /seed`) is intentionally **not** exposed as
an agent tool — it is an internal/test utility. Only the 7 CRUD tools are
available to the agent: `create_event`, `get_event`, `list_events`,
`update_event`, `delete_event`, `batch_upsert`, and `clear_all_events`.

### System prompt
`agent/system_prompt.py` builds the prompt lazily at call time (not at import
time) so it always reflects the live tool list and the current New York
date/time. The user's sleep preferences from `user-prefs.json` are appended to
the system message at startup.

## Tests

A pytest suite exercises every endpoint, including validation, range-query
boundary semantics, batch upsert atomicity, DST/timezone conversion, and seed
idempotency. Tests run against an isolated in-memory SQLite DB (no file
artifacts).

```bash
make test-unit          # or: uv run pytest tests/
```

The standalone smoke script (requires a running API):

```bash
make smoke              # or: uv run python scripts/smoke_test.py
```

## Evals

The `evals/` directory contains a four-layer agent evaluation suite designed to
catch regressions in tool routing, prompt construction, agent-loop mechanics,
and end-to-end scheduling behaviour.

### Running evals

```bash
# Layers 1 & 2: deterministic, no LLM, no network — runs in <1s
make test-evals         # or: uv run pytest evals/test_dispatch.py evals/test_prompt.py \
                        #        evals/test_agent_loop.py evals/test_sleep_guard.py::TestJudgeParser

# Layers 3 & 4: live LLM (requires OPENROUTER_API_KEY in .env)
make test-evals-live    # or: uv run pytest evals/test_scenarios.py evals/test_event_order.py \
                        #        evals/test_sleep_guard.py

# Run everything (API tests + all evals)
make test               # or: uv run pytest

# Target a specific failure-mode tag
uv run pytest evals/test_scenarios.py -k "negation"
uv run pytest evals/test_scenarios.py -k "dense_schedule"
```

Live-LLM tests are automatically skipped when `OPENROUTER_API_KEY` is not set.

### Eval structure

```
evals/
  conftest.py          # Shared fixtures: in-memory API client, sleep-window helpers
  fake_llm.py          # Scripted fake OpenAI client for Layer 2 tests
  judge.py             # LLM-as-Judge: SleepGuardRubric, EventOrderRubric
  scenarios.py         # EvalScenario dataclass, 50 scenario definitions, setup helpers
  test_dispatch.py     # Layer 1a: tool dispatch routing (mocked httpx)
  test_prompt.py       # Layer 1b/c: system prompt integrity + tool schema compliance
  test_agent_loop.py   # Layer 2: agent loop with scripted fake LLM
  test_scenarios.py    # Layer 3: oracle-based end-to-end scenarios (live LLM)
  test_event_order.py  # Layer 4: event-ordering reasonableness (LLM-as-Judge)
  test_sleep_guard.py  # Layer 4: sleep-protection adversarials (LLM-as-Judge)
```

### Layer 1 — Deterministic unit evals (no LLM, no network)

- **`test_dispatch.py`** — Every tool name maps to the correct HTTP verb, URL,
  and payload. Verifies `event_id` is stripped from PATCH bodies, query params
  are forwarded correctly, and unknown tools return errors.
- **`test_prompt.py`** — System prompt contains the current NY time, mentions
  all tools, includes sleep-protection language. Tool schemas are valid
  (required params exist in properties, types are valid JSON Schema, no
  duplicates, all snake_case).

### Layer 2 — Agent loop with scripted LLM

- **`test_agent_loop.py`** — Drives `_run_turn()` with a `FakeLLMClient` that
  replays predetermined tool-call / text sequences. Tests single and multi-step
  tool chains, parallel tool calls, error propagation, conversation history
  growth, and tool-call ID forwarding.

### Layer 3 — Oracle-based end-to-end scenarios (live LLM)

- **`test_scenarios.py`** — 50 scenarios, each with a user message and an
  oracle function that checks the final calendar state and agent reply.
  Scenarios cover:

  | Tag                  | Count | Tests                                                    |
  |----------------------|-------|----------------------------------------------------------|
  | `create`             | 20    | Simple, batch, with-location, duration inference         |
  | `read`               | 2     | List today, describe sleep block                         |
  | `update`             | 4     | Reschedule, rename, move-to-gap                          |
  | `delete`             | 6     | Cancel, clear-all, selective deletion                    |
  | `sleep-protection`   | 7     | Direct conflict, wind-down overlap, boundary edges       |
  | `event-order`        | 6     | Workout→shower, cook→eat, morning routine chains         |
  | `dense-schedule`     | 5     | Packed workday: cancel meetings, find gaps, prioritize   |
  | `messy-input`        | 2     | Stream-of-consciousness brain dump with ~7 events        |
  | `relative-time`      | 3     | "In 3 hours", "next Tuesday", "day after tomorrow"       |
  | `midnight-confusion` | 2     | "Tonight at 1am", events ending at midnight              |
  | `double-booking`     | 2     | Overlap within request, overlap with existing event      |
  | `duration-inference` | 2     | No end time given, "quick coffee"                        |
  | `conditional`        | 2     | "If free at 3pm, add gym" (busy / free variants)         |
  | `idempotency`        | 2     | Duplicate detection, same-title-different-time           |
  | `negation`           | 3     | "EXCEPT the gym", "delete all but date", "NOT morning"   |
  | `retroactive`        | 2     | Query past events, read actual sleep end time            |
  | `arithmetic`         | 2     | Sum meeting hours, compute free time in a range          |
  | `dangerous-tool`     | 2     | "Start fresh" shouldn't nuke, seed not called by user    |
  | `timezone`           | 1     | "3pm UTC" → NY local conversion                          |
  | `implicit-dependency`| 1     | Shower survives workout→shower→date chain                |
  | `prioritization`     | 2     | Running behind: keep workout + date, drop the right stuff|

  Each scenario optionally seeds or uses a custom `setup` function (e.g.
  `_setup_dense_schedule` populates a 15-event packed workday).

### Layer 4 — LLM-as-Judge

- **`test_sleep_guard.py`** — Adversarial sleep-conflict prompts scored by a
  judge LLM on a 0–2 rubric (`SleepGuardRubric`). Includes "just this once",
  "only 30 minutes", "don't worry about sleep" phrasings.
- **`test_event_order.py`** — Event-ordering scenarios scored by
  `EventOrderRubric`. Checks workout→shower, cook→eat, grocery→cook→dinner,
  commute→meeting, and full morning-routine chains.

### Adding a new scenario

1. Define an `EvalScenario` in `evals/scenarios.py` with a `name`,
   `user_message`, `oracle` function, and `tags`.
2. Optionally add a `setup` callable that populates the calendar via the
   TestClient before the agent runs (see `_setup_dense_schedule` for an
   example).
3. The scenario is automatically picked up by `test_scenarios.py`'s
   parametrized test. Tag-filtered test functions (e.g.
   `test_sleep_protection_scenario`) also pick it up if the tags match.
4. For judge-scored scenarios, add a test in `test_event_order.py` or
   `test_sleep_guard.py` that calls `_run_scenario` and passes the result
   to a `Judge` with the appropriate rubric.

## Makefile

All common workflows have `make` shortcuts. Run `make help` to list them:

| Target | Description |
|--------|-------------|
| `make help` | Show all available targets |
| `make api` | Start the calendar API locally (without Docker) |
| `make agent` | Start the agent REPL |
| `make test` | Run all tests and evals |
| `make test-unit` | Run API unit tests only |
| `make test-evals` | Run deterministic evals (no LLM) |
| `make test-evals-live` | Run live-LLM evals |
| `make smoke` | Run the standalone smoke test script |
| `make docker-build` | Build the Docker image |
| `make docker-up` | Start the API in Docker |
| `make docker-down` | Stop the Docker container |
| `make docker-logs` | Tail Docker container logs |
| `make docker-reset` | Stop and delete the database volume |
