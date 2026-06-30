"""
Layer 3 — Oracle-based end-to-end scenario tests.

Runs each EvalScenario in SCENARIOS against:
  * the real FastAPI app (backed by an in-memory SQLite DB), and
  * the real LLM via OpenRouter.

Tests are skipped automatically when OPENROUTER_API_KEY is not set so CI
without a key stays green on Layers 1 & 2.

Architecture
────────────
1.  An in-memory TestClient serves the calendar API.
2.  The agent.tools HTTP calls are redirected to that TestClient via a
    custom httpx.MockTransport so no sockets are opened.
3.  _run_turn() is called directly with a real OpenAI client (OpenRouter).
4.  After the agent finishes, we query GET /events to read the final state
    and pass it to the scenario's oracle function.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import mock_calendar_api.db as db
from agent.main import MODEL, _run_turn
from agent.system_prompt import get_system_prompt
from agent.tools import TOOLS
from evals.conftest import PREFS, has_api_key
from evals.scenarios import SCENARIOS, EvalScenario
from mock_calendar_api.api import app
from mock_calendar_api.db import init_db


# ── Live-API redirect transport ───────────────────────────────────────────────

class _TestClientTransport(httpx.BaseTransport):
    """
    Routes every httpx request made by agent.tools through a Starlette
    TestClient instead of a real socket.  This lets the agent call the
    calendar API at its configured CALENDAR_API_URL without a live server.
    """

    def __init__(self, starlette_client: TestClient) -> None:
        self._client = starlette_client

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        # Build a relative URL (path + query) that the TestClient understands.
        url = request.url.path
        if request.url.query:
            # request.url.query is bytes; decode to str for TestClient.
            raw_query = request.url.query
            query_str = raw_query.decode() if isinstance(raw_query, bytes) else raw_query
            url = f"{url}?{query_str}"
        content = request.content
        headers = dict(request.headers)

        resp = self._client.request(
            method=method,
            url=url,
            content=content,
            headers={k: v for k, v in headers.items() if k.lower() != "host"},
        )
        return httpx.Response(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            content=resp.content,
        )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def isolated_api() -> Iterator[TestClient]:
    """Fresh in-memory calendar API for each scenario."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original = db.engine
    db.engine = test_engine
    init_db()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        db.engine = original


@pytest.fixture()
def openrouter_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY not set")
    return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_scenario(
    scenario: EvalScenario,
    api_client: TestClient,
    llm_client: OpenAI,
) -> tuple[str, list[dict]]:
    """
    Execute one scenario end-to-end.

    Returns (agent_reply, final_event_list).
    """
    # 1. Optionally seed the calendar.
    if scenario.seed:
        api_client.post("/seed", params={"replace": "true"})

    # 2. Build a transport that routes httpx → in-memory TestClient.
    transport = _TestClientTransport(api_client)

    # 3. Patch httpx.get/post/patch/delete to use the transport-backed client.
    #    agent.tools uses httpx.get / httpx.post / httpx.patch / httpx.delete
    #    directly, so we replace them with a bound httpx.Client.
    bound = httpx.Client(transport=transport, base_url="http://testserver")

    def _get(path: str, params=None):
        r = bound.get(path, params=params, timeout=10)
        r.raise_for_status()
        return r.json() if r.content else None

    def _post(path: str, body=None, params=None):
        r = bound.post(path, json=body, params=params, timeout=10)
        r.raise_for_status()
        return r.json() if r.content else None

    def _patch(path: str, body=None):
        r = bound.patch(path, json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    def _delete(path: str):
        r = bound.delete(path, timeout=10)
        r.raise_for_status()
        return r.json() if r.content else {"status": "deleted"}

    # 4. Build system prompt and run the agent turn.
    system_content = get_system_prompt()
    prefs_note = (
        f"\n[User sleep preferences — bedtime: {PREFS['bedtime']}, "
        f"waketime: {PREFS['waketime']}, "
        f"wind-down: {PREFS['wind_down_mins']} mins]"
    )
    messages: list[dict] = [
        {"role": "system", "content": system_content + prefs_note},
        {"role": "user", "content": scenario.user_message},
    ]

    with (
        patch("agent.tools._get", side_effect=_get),
        patch("agent.tools._post", side_effect=_post),
        patch("agent.tools._patch", side_effect=_patch),
        patch("agent.tools._delete", side_effect=_delete),
    ):
        reply = _run_turn(llm_client, messages)

    # 5. Read the final calendar state through the same in-memory DB.
    final_events = api_client.get("/events").json()
    return reply, final_events


# ── Parametrized test ─────────────────────────────────────────────────────────

@has_api_key
@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=[s.name for s in SCENARIOS],
)
def test_scenario(scenario: EvalScenario, isolated_api: TestClient, openrouter_client: OpenAI):
    """Run one scenario, check its oracle, and report failures with context."""
    reply, final_events = _run_scenario(scenario, isolated_api, openrouter_client)

    passed = scenario.oracle(final_events, reply)

    if not passed:
        event_titles = [e["title"] for e in final_events]
        pytest.fail(
            f"\nScenario   : {scenario.name}\n"
            f"Tags       : {scenario.tags}\n"
            f"Prompt     : {scenario.user_message!r}\n"
            f"Description: {scenario.description}\n"
            f"Agent reply: {reply!r}\n"
            f"Final titles: {event_titles}\n"
        )


# ── Tag-group smoke tests (subsets) ───────────────────────────────────────────
# These run the same scenarios but let you target a subset with -k in CI.

@has_api_key
@pytest.mark.parametrize(
    "scenario",
    [s for s in SCENARIOS if "sleep-protection" in s.tags],
    ids=[s.name for s in SCENARIOS if "sleep-protection" in s.tags],
)
def test_sleep_protection_scenario(
    scenario: EvalScenario, isolated_api: TestClient, openrouter_client: OpenAI
):
    """Dedicated run for sleep-protection scenarios — useful for focused CI jobs."""
    reply, final_events = _run_scenario(scenario, isolated_api, openrouter_client)
    passed = scenario.oracle(final_events, reply)
    if not passed:
        pytest.fail(
            f"[SLEEP PROTECTION] {scenario.name} failed.\n"
            f"Reply: {reply!r}\n"
            f"Events: {[e['title'] for e in final_events]}"
        )
