# Sleep Calendar Agent

A sleep-focused calendar scheduling agent backed by a mock calendar HTTP API.
You talk to the agent in plain English; it calls the calendar API on your behalf
while treating your sleep block as inviolable.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/) | Docker ≥ 20, Compose v2 | Run the mock calendar API |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | ≥ 0.9 | Python package/project manager (runs the agent & tests) |
| Python | ≥ 3.13 | Required by the project; uv will install it automatically if missing |

You also need an [OpenRouter](https://openrouter.ai) API key to run the agent
and the live-LLM evaluation layers.

## Setup

**1. Clone and enter the repo**

```bash
git clone <repo-url>
cd sleep-calendar-agent
```

**2. Create a `.env` file**

```env
OPENROUTER_API_KEY=sk-or-...
CALENDAR_API_URL=http://127.0.0.1:8000
```

`CALENDAR_API_URL` defaults to `http://127.0.0.1:8000` if omitted.

**3. (Optional) Edit sleep preferences**

`user-prefs.json` ships with sensible defaults:

```json
{
  "bedtime": "12:30 AM",
  "waketime": "8:15 AM",
  "wind_down_mins": 90
}
```

## Running the mock calendar API (Docker)

```bash
# Build and start the API in the background
make up          # or: docker compose up -d

# Verify it's running
curl http://127.0.0.1:8000/events    # → []

# View logs
make logs        # or: docker compose logs -f

# Stop
make down        # or: docker compose down

# Stop and delete the database volume
make reset       # or: docker compose down -v
```

The API serves on **http://127.0.0.1:8000** with interactive Swagger docs at
**http://127.0.0.1:8000/docs**. The SQLite database is persisted in a Docker
volume so data survives container restarts.

## Running the agent

With the calendar API running:

```bash
make agent              # or: uv run python agent/main.py
```

Type any scheduling request in plain English. The agent calls calendar tools as
needed and confirms changes in plain language. Type `exit`, `quit`, or `bye`
(or press `Ctrl-C` / `Ctrl-D`) to quit.

## Running tests

```bash
# All tests and evals
make test               # or: uv run pytest

# API unit tests only (no network, no LLM)
make test-unit          # or: uv run pytest tests/

# Deterministic evals (no network, no LLM)
make test-evals         # or: uv run pytest evals/test_dispatch.py evals/test_prompt.py \
                        #        evals/test_agent_loop.py evals/test_sleep_guard.py::TestJudgeParser

# Live-LLM evals (requires OPENROUTER_API_KEY)
make test-evals-live    # or: uv run pytest evals/test_scenarios.py evals/test_event_order.py \
                        #        evals/test_sleep_guard.py

# Standalone smoke test against a running API
make smoke              # or: uv run python scripts/smoke_test.py
```

Live-LLM tests are automatically skipped when `OPENROUTER_API_KEY` is not set.

## Makefile reference

Run `make help` to see all targets:

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
| `make build` | Build the Docker image |
| `make up` | Start the API in Docker |
| `make down` | Stop the Docker container |
| `make logs` | Tail Docker container logs |
| `make reset` | Stop and delete the database volume |
