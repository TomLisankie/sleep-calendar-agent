"""
Layer 4 — Event-ordering reasonableness tests with LLM-as-Judge.

Verifies that when the agent schedules multiple activities with a natural
real-world dependency (workout → shower, cooking → eating, commute → meeting,
etc.), the events appear in a sensible chronological order.

The oracle in each scenario only checks that the right events *exist*.  The
`EventOrderRubric` judge then scores whether their order makes real-world
sense.

Tests are skipped when OPENROUTER_API_KEY is not set.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from openai import OpenAI
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import mock_calendar_api.db as db
from evals.conftest import has_api_key
from evals.judge import EventOrderRubric, Judge
from evals.scenarios import SCENARIOS, EvalScenario
from evals.test_scenarios import _run_scenario
from mock_calendar_api.api import app
from mock_calendar_api.db import init_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def isolated_api():
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
def llm_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY not set")
    return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")


@pytest.fixture()
def judge(llm_client) -> Judge:
    return Judge(llm_client)


@pytest.fixture()
def rubric() -> EventOrderRubric:
    return EventOrderRubric()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_order_score(
    judge: Judge,
    rubric: EventOrderRubric,
    scenario: EvalScenario,
    reply: str,
    final_events: list[dict],
    min_score: int = 2,
) -> None:
    result = judge.score(rubric, scenario.user_message, reply, final_events)
    print(
        f"\n[judge:event-order] {scenario.name}\n"
        f"  score : {result.score}/2\n"
        f"  reason: {result.reason}\n"
        f"  events: {[(e['title'], e['start'][:16]) for e in final_events]}"
    )
    if result.score < min_score:
        pytest.fail(
            f"Event-order judge score {result.score} < required {min_score} "
            f"for scenario '{scenario.name}'.\n"
            f"Reason: {result.reason}\n"
            f"Agent reply: {reply!r}\n"
            f"Events (title → start): "
            f"{[(e['title'], e['start']) for e in final_events]}"
        )


# ── Parametrized event-order tests ───────────────────────────────────────────

_ORDER_SCENARIOS = [s for s in SCENARIOS if "event-order" in s.tags]


@has_api_key
@pytest.mark.parametrize(
    "scenario",
    _ORDER_SCENARIOS,
    ids=[s.name for s in _ORDER_SCENARIOS],
)
def test_event_order(
    scenario: EvalScenario,
    isolated_api: TestClient,
    llm_client: OpenAI,
    judge: Judge,
    rubric: EventOrderRubric,
):
    """
    Run the scenario, verify the oracle (events exist), then judge ordering.
    """
    reply, final_events = _run_scenario(scenario, isolated_api, llm_client)

    # First: oracle — the right events must exist.
    oracle_passed = scenario.oracle(final_events, reply)
    if not oracle_passed:
        pytest.fail(
            f"Oracle failed for '{scenario.name}' — expected events not found.\n"
            f"Reply: {reply!r}\n"
            f"Events: {[e['title'] for e in final_events]}"
        )

    # Then: judge — the ordering must be sensible.
    _assert_order_score(judge, rubric, scenario, reply, final_events)
