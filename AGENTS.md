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
user-prefs.json    # User sleep preferences (bedtime, waketime, wind_down_mins)
.env               # OPENROUTER_API_KEY and CALENDAR_API_URL
```

## Quickstart

**1. Start the calendar API**

```bash
uv run python main.py        # serves on http://127.0.0.1:8000
# or: uv run uvicorn mock_calendar_api.app:app --reload
```

Interactive docs are available at `http://127.0.0.1:8000/docs`. The SQLite file
`calendar.db` is created next to the app on first run.

**2. Start the agent**

```bash
uv run python agent/main.py
```

The agent reads sleep preferences from `user-prefs.json`, injects the current
New York time into the system prompt, then opens a terminal REPL. Type any
scheduling request in plain English; the agent calls calendar tools as needed
and confirms changes in plain language. Type `exit`, `quit`, or `bye` (or
`Ctrl-C` / `Ctrl-D`) to quit.

**3. Configure**

`.env`:
```
OPENROUTER_API_KEY=sk-or-...
CALENDAR_API_URL=http://127.0.0.1:8000   # default
```

`user-prefs.json`:
```json
{
  "bedtime": "12:30 AM",
  "waketime": "8:15 AM",
  "wind_down_mins": 90
}
```

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
uv run pytest
```

The standalone smoke script is also available:

```bash
uv run python scripts/smoke_test.py
```
