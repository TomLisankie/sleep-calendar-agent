.PHONY: help api agent test test-unit test-evals test-evals-live smoke \
       docker-up docker-down docker-build docker-logs docker-reset lint fmt

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Local development
# ---------------------------------------------------------------------------

api: ## Start the calendar API locally
	uv run python main.py

agent: ## Start the agent REPL
	uv run python agent/main.py

# ---------------------------------------------------------------------------
# Tests & evals
# ---------------------------------------------------------------------------

test: ## Run all tests and evals
	uv run pytest

test-unit: ## Run API unit tests only
	uv run pytest tests/

test-evals: ## Run deterministic evals (no LLM, no network)
	uv run pytest evals/test_dispatch.py evals/test_prompt.py evals/test_agent_loop.py evals/test_sleep_guard.py::TestJudgeParser

test-evals-live: ## Run live-LLM evals (requires OPENROUTER_API_KEY)
	uv run pytest evals/test_scenarios.py evals/test_event_order.py evals/test_sleep_guard.py

smoke: ## Run the standalone smoke test script
	uv run python scripts/smoke_test.py

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

build: ## Build the Docker image
	docker compose build

up: ## Start the API in Docker (builds if needed)
	docker compose up -d

down: ## Stop the Docker container
	docker compose down

logs: ## Tail Docker container logs
	docker compose logs -f

reset: ## Stop containers and delete the database volume
	docker compose down -v
