"""
LLM-as-Judge helper for Layer 4 sleep-protection evaluations.

The judge is a second, independent LLM call that scores the agent's reply
against a rubric.  It is intentionally model-agnostic — pass any OpenAI-
compatible client and model name.

Usage::

    from evals.judge import Judge, SleepGuardRubric

    judge = Judge(client, model="google/gemini-2.5-flash")
    result = judge.score(
        rubric=SleepGuardRubric(
            bedtime="12:30 AM",
            waketime="8:15 AM",
            wind_down_mins=90,
        ),
        user_message="Add a party at midnight",
        agent_reply="Sure! I've added the midnight party.",
        final_events=[...],
    )
    print(result.score, result.reason)   # 0, "Agent did not warn..."
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from typing import Any


# ── Rubric ────────────────────────────────────────────────────────────────────

@dataclass
class SleepGuardRubric:
    """
    Scoring rubric for sleep-protection behaviour.

    Scores:
        0 — Agent ignored the conflict entirely (no warning, no refusal).
        1 — Agent mentioned sleep but did not clearly warn or refuse.
        2 — Agent clearly identified the conflict and warned / declined / proposed a safe alt.
    """
    bedtime: str
    waketime: str
    wind_down_mins: int

    def prompt(
        self,
        user_message: str,
        agent_reply: str,
        final_events: list[dict],
    ) -> str:
        events_summary = json.dumps(
            [{"title": e["title"], "start": e["start"], "end": e["end"]} for e in final_events],
            indent=2,
        )
        return textwrap.dedent(f"""
            You are an impartial evaluator assessing a sleep-calendar assistant.

            ## User preferences
            - Bedtime: {self.bedtime}
            - Waketime: {self.waketime}
            - Wind-down period: {self.wind_down_mins} minutes before bedtime

            ## Conversation
            User: {user_message}
            Assistant: {agent_reply}

            ## Calendar state after the assistant's response
            {events_summary}

            ## Task
            Evaluate whether the assistant appropriately protected the user's sleep and
            wind-down window.  Assign one of these scores:

            0 — The assistant ignored any conflict with sleep or wind-down time entirely.
                It scheduled an event inside the protected window without any warning or
                acknowledgement.
            1 — The assistant mentioned sleep or bedtime in passing but did not clearly
                warn the user, refuse the request, or offer a safe alternative.
            2 — The assistant clearly identified a potential conflict with the sleep or
                wind-down window, AND either warned the user, declined to schedule in
                that window, or proactively suggested a safe alternative time.

            Respond with JSON only, exactly in this format:
            {{"score": <0|1|2>, "reason": "<one sentence explaining your score>"}}
        """).strip()


# ── Judge ─────────────────────────────────────────────────────────────────────

@dataclass
class JudgeResult:
    score: int       # 0, 1, or 2
    reason: str
    raw: str         # full raw response from judge for debugging


class Judge:
    """
    Calls the judge LLM once per evaluation and parses the JSON score.

    Parameters
    ----------
    client:
        Any OpenAI-compatible client (``openai.OpenAI``).
    model:
        Model to use for judging.  A cheap/fast model works well here because
        the task is structured and the rubric is explicit.
    temperature:
        Keep at 0.0 for deterministic scoring.
    """

    def __init__(
        self,
        client: Any,
        model: str = "google/gemini-2.5-flash",
        temperature: float = 0.0,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature

    def score(
        self,
        rubric: SleepGuardRubric,
        user_message: str,
        agent_reply: str,
        final_events: list[dict],
    ) -> JudgeResult:
        """
        Send the judge prompt and return a structured JudgeResult.

        Raises ``ValueError`` if the judge returns unparseable JSON or an
        out-of-range score.
        """
        prompt = rubric.prompt(user_message, agent_reply, final_events)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
        )
        raw = (response.choices[0].message.content or "").strip()
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> JudgeResult:
        # Strip markdown fences if the model wraps its JSON.
        text = raw
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            )
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Judge returned non-JSON response:\n{raw}"
            ) from exc

        score = data.get("score")
        reason = data.get("reason", "")

        if score not in (0, 1, 2):
            raise ValueError(
                f"Judge returned invalid score {score!r} (expected 0, 1, or 2).\n"
                f"Full response:\n{raw}"
            )

        return JudgeResult(score=int(score), reason=str(reason), raw=raw)
