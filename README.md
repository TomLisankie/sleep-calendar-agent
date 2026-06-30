# What it is

A calendar scheduling agent which treats sleep as the most important part of the day and tries whenever possible to not mess with it.

# Architecture
- Mock calendar API. This is in place of, say, the Google Calendar API so that you don't have to plug your actual calendar in just to try it out.
- User preferences file. This holds basic user preferences related to sleep.
- A standard agent loop. This agent takes in user queries related to scheduling and performs calendaring actions using the tools it's provided with in order to make the necessary changes to the calendar. Available tools are provided to the LLM in the OpenAI function calling format.

# Coding Agent
I used the [Pi coding agent](https://pi.dev/) with a mix of GLM 5.2, Claude Sonnet 4.6, and Claude Opus 4.6. I started with GLM 5.2 because it's really good at coding for the price. However, I ran into capacity constraints so switched over to Claude models because I've found them to be really nice at coding although they're more expensive.

# Evaluation
Before considering agent behavior, I first wanted to consider the stability of the harness and its ability to properly call tools in various scenarios (no tools needed, multiple tool calls chained together, etc.). This is important because the LLM could generate excellent behavior but it doesn't matter if the harness can't execute any of it.

Next up was testing agent behavior. There are an enormous number of valid schedules for a given query so it's unimportant to see if a schedule matches a particular example verbatim and is instead important to make sure certain structural (ex. all mentioned events in the user query were added) and semantic (ex. don't add a shower event right before a workout event) properties are met. Also important is taking into account social logic (ex. it should double check with you if fulfilling your scheduling goal would involve canceling a meeting since that doesn't just affect you). I tried to represent these kinds of scenarios accurately in my evaluation suite. I used programmatic checks for structural requirements and some semantic requirements. To test whether the agent was correctly invoking concerns about events flowing into sleep time, I used an LLM-as-judge setup.

# Usage and Installation

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
