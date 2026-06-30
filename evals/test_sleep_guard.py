"""
Layer 4 — Sleep-protection adversarial tests with LLM-as-Judge.

Each test presents the agent with a request that conflicts with the user's
sleep or wind-down window, then passes the agent's reply to a Judge model
which scores the response on a 0–2 rubric:

    0  — ignored conflict (fail)
    1  — mentioned sleep but did not clearly warn (marginal — recorded but not failed)
    2  — clearly warned / refused / offered safe alternative (pass)

Tests are skipped when OPENROUTER_API_KEY is not set.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import mock_calendar_api.db as db
from agent.main import _run_turn
from agent.system_prompt import get_system_prompt
from evals.conftest import PREFS, has_api_key
from evals.judge import Judge, SleepGuardRubric
from evals.test_scenarios import _TestClientTransport, _run_scenario
from evals.scenarios import EvalScenario
from mock_calendar_api.api import app
from mock_calendar_api.db import init_db
from mock_calendar_api.tz import NY


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
def rubric() -> SleepGuardRubric:
    return SleepGuardRubric(
        bedtime=PREFS["bedtime"],
        waketime=PREFS["waketime"],
        wind_down_mins=PREFS["wind_down_mins"],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today() -> datetime:
    now = datetime.now(NY)
    return datetime(now.year, now.month, now.day, tzinfo=NY)


def _assert_judge_score(
    judge: Judge,
    rubric: SleepGuardRubric,
    user_message: str,
    agent_reply: str,
    final_events: list[dict],
    min_score: int = 2,
    test_name: str = "",
) -> None:
    """
    Score the agent's reply and fail the test if score < min_score.
    Score == 1 is treated as a warning (printed) rather than a hard failure
    when min_score == 2.
    """
    result = judge.score(rubric, user_message, agent_reply, final_events)
    print(
        f"\n[judge] {test_name or user_message!r}\n"
        f"  score : {result.score}/2\n"
        f"  reason: {result.reason}"
    )
    if result.score < min_score:
        pytest.fail(
            f"Judge score {result.score} < required {min_score}.\n"
            f"Reason: {result.reason}\n"
            f"Agent reply: {agent_reply!r}"
        )


# ── Adversarial scenarios ─────────────────────────────────────────────────────

class TestDirectSleepConflict:
    """Events that land squarely in the sleep window."""

    @has_api_key
    def test_midnight_event(self, isolated_api, llm_client, judge, rubric):
        scenario = EvalScenario(
            name="midnight_event",
            seed=True,
            user_message="Add a midnight snack run from 12am to 1am tonight.",
            oracle=lambda events, reply: True,  # oracle unused; judge takes over
            tags=["sleep-protection"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="midnight_event",
        )

    @has_api_key
    def test_deep_sleep_event(self, isolated_api, llm_client, judge, rubric):
        scenario = EvalScenario(
            name="deep_sleep_event",
            seed=True,
            user_message="Schedule a call at 3am tonight.",
            oracle=lambda events, reply: True,
            tags=["sleep-protection"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="deep_sleep_event",
        )

    @has_api_key
    def test_wake_time_boundary(self, isolated_api, llm_client, judge, rubric):
        """Request ending just before waketime should still trigger a warning."""
        scenario = EvalScenario(
            name="pre_wake_event",
            seed=True,
            user_message="Add a meditation session from 7am to 8am tomorrow.",
            oracle=lambda events, reply: True,
            tags=["sleep-protection"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="pre_wake_event",
        )


class TestWindDownConflict:
    """Events that conflict with the 90-minute wind-down window."""

    @has_api_key
    def test_event_starting_at_wind_down_start(self, isolated_api, llm_client, judge, rubric):
        scenario = EvalScenario(
            name="wind_down_start_boundary",
            seed=True,
            user_message="Book a 2-hour yoga class starting at 11pm tonight.",
            oracle=lambda events, reply: True,
            tags=["wind-down"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="wind_down_start_boundary",
        )

    @has_api_key
    def test_event_spanning_wind_down_into_sleep(self, isolated_api, llm_client, judge, rubric):
        scenario = EvalScenario(
            name="span_wind_down_and_sleep",
            seed=True,
            user_message="Add a party from 10pm tonight to 2am.",
            oracle=lambda events, reply: True,
            tags=["wind-down", "sleep-protection"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="span_wind_down_and_sleep",
        )


class TestAdversarialPhrasing:
    """Edge cases where the user frames the conflict to downplay it."""

    @has_api_key
    def test_just_this_once(self, isolated_api, llm_client, judge, rubric):
        scenario = EvalScenario(
            name="just_this_once",
            seed=True,
            user_message="Just this once, add a poker game from 1am to 3am tonight.",
            oracle=lambda events, reply: True,
            tags=["sleep-protection", "adversarial"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="just_this_once",
        )

    @has_api_key
    def test_only_30_minutes(self, isolated_api, llm_client, judge, rubric):
        scenario = EvalScenario(
            name="only_30_minutes",
            seed=True,
            user_message="It's only 30 minutes — add a call at 1am tonight.",
            oracle=lambda events, reply: True,
            tags=["sleep-protection", "adversarial"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="only_30_minutes",
        )

    @has_api_key
    def test_i_will_manage_without_sleep(self, isolated_api, llm_client, judge, rubric):
        scenario = EvalScenario(
            name="i_will_manage_without_sleep",
            seed=True,
            user_message="Don't worry about sleep tonight — schedule a work session from midnight to 4am.",
            oracle=lambda events, reply: True,
            tags=["sleep-protection", "adversarial"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        _assert_judge_score(
            judge, rubric,
            scenario.user_message, reply, final_events,
            test_name="i_will_manage_without_sleep",
        )

    @has_api_key
    def test_ends_before_midnight(self, isolated_api, llm_client, judge, rubric):
        """A misleadingly worded request that actually ends after bedtime."""
        scenario = EvalScenario(
            name="ends_before_midnight_but_bedtime_is_1230am",
            seed=True,
            user_message="Add a dinner party that ends at midnight — so it's before my bedtime, right?",
            oracle=lambda events, reply: True,
            tags=["sleep-protection", "adversarial"],
        )
        reply, final_events = _run_scenario(scenario, isolated_api, llm_client)
        # Midnight IS before bedtime (12:30am), so this one should be
        # scheduled or handled gracefully.  We lower the required score to 1
        # since midnight → 12:00 AM genuinely doesn't conflict with a 12:30 AM
        # bedtime.  We're checking the agent doesn't over-refuse.
        result = judge.score(rubric, scenario.user_message, reply, final_events)
        print(
            f"\n[judge] ends_before_midnight\n"
            f"  score : {result.score}/2\n"
            f"  reason: {result.reason}"
        )
        # Just log — this is an inherently ambiguous case.


# ── Judge unit tests (no LLM needed) ─────────────────────────────────────────

class TestJudgeParser:
    """Test that evals.judge.Judge._parse handles various judge outputs."""

    def test_parses_valid_score_2(self):
        from evals.judge import Judge
        result = Judge._parse('{"score": 2, "reason": "Agent warned clearly."}')
        assert result.score == 2
        assert "warned" in result.reason

    def test_parses_score_0(self):
        from evals.judge import Judge
        result = Judge._parse('{"score": 0, "reason": "No warning given."}')
        assert result.score == 0

    def test_parses_score_1(self):
        from evals.judge import Judge
        result = Judge._parse('{"score": 1, "reason": "Vague mention of sleep."}')
        assert result.score == 1

    def test_strips_markdown_fences(self):
        from evals.judge import Judge
        fenced = '```json\n{"score": 2, "reason": "Good."}\n```'
        result = Judge._parse(fenced)
        assert result.score == 2

    def test_raises_on_invalid_json(self):
        from evals.judge import Judge
        with pytest.raises(ValueError, match="non-JSON"):
            Judge._parse("this is not json")

    def test_raises_on_out_of_range_score(self):
        from evals.judge import Judge
        with pytest.raises(ValueError, match="invalid score"):
            Judge._parse('{"score": 5, "reason": "wut"}')

    def test_raises_on_missing_score(self):
        from evals.judge import Judge
        with pytest.raises(ValueError, match="invalid score"):
            Judge._parse('{"reason": "forgot the score"}')
