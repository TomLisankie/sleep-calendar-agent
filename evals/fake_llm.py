"""
Scripted fake OpenAI client for testing agent.main._run_turn without real LLM
calls.

Each *step* in the script corresponds to exactly one call to
``client.chat.completions.create()``.  Steps are:

* ``TextStep(text)``          — assistant returns a plain text reply (no tools)
* ``ToolCallStep(...)``       — assistant returns a single tool call
* ``MultiToolCallStep(...)``  — assistant returns multiple tool calls in one turn

Usage::

    from evals.fake_llm import FakeLLMClient, MultiToolCallStep, TextStep, ToolCallSpec, ToolCallStep

    client = FakeLLMClient([
        ToolCallStep("list_events", {"start": "2026-07-01T00:00:00"}),
        TextStep("You have 3 events this week."),
    ])
    reply = _run_turn(client, messages)
    assert client.call_count == 2
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ── Script step types ─────────────────────────────────────────────────────────


@dataclass
class ToolCallSpec:
    """One tool-call entry within a single LLM response."""

    tool_name: str
    arguments: dict
    call_id: str = "tc_test"


@dataclass
class ToolCallStep:
    """LLM response containing exactly one tool call."""

    tool_name: str
    arguments: dict
    call_id: str = "tc_test_001"

    def to_spec(self) -> ToolCallSpec:
        return ToolCallSpec(self.tool_name, self.arguments, self.call_id)


@dataclass
class MultiToolCallStep:
    """LLM response that contains multiple tool calls in a single turn."""

    specs: list[ToolCallSpec]


@dataclass
class TextStep:
    """LLM response with a plain text reply and no tool calls."""

    text: str


# ── Internal fake response objects ───────────────────────────────────────────


@dataclass
class _FakeFunction:
    name: str
    arguments: str  # JSON-encoded string, as in the real OpenAI SDK


@dataclass
class _FakeToolCall:
    id: str
    function: _FakeFunction


class _FakeMessage:
    """Mimics openai.types.chat.ChatCompletionMessage well enough for _run_turn."""

    def __init__(
        self,
        content: str | None,
        tool_calls: list[_FakeToolCall],
    ) -> None:
        self.content = content
        # Empty list is falsy — matches the `if not message.tool_calls` guard.
        self.tool_calls = tool_calls

    def model_dump(self, **kwargs: Any) -> dict:  # noqa: ARG002
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": (
                [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in self.tool_calls
                ]
                if self.tool_calls
                else None
            ),
        }


class _FakeResponse:
    def __init__(self, message: _FakeMessage) -> None:
        _choice = type("_Choice", (), {"message": message})()
        self.choices = [_choice]


def _step_to_message(
    step: TextStep | ToolCallStep | MultiToolCallStep,
) -> _FakeMessage:
    if isinstance(step, TextStep):
        return _FakeMessage(content=step.text, tool_calls=[])

    specs: list[ToolCallSpec] = (
        [step.to_spec()] if isinstance(step, ToolCallStep) else step.specs
    )
    tool_calls = [
        _FakeToolCall(
            id=spec.call_id,
            function=_FakeFunction(
                name=spec.tool_name,
                arguments=json.dumps(spec.arguments),
            ),
        )
        for spec in specs
    ]
    return _FakeMessage(content=None, tool_calls=tool_calls)


# ── Public client class ───────────────────────────────────────────────────────


class FakeLLMClient:
    """
    Scripted fake OpenAI-compatible client.

    Replays a fixed list of steps in order.  Raises ``IndexError`` if more
    calls are made than steps were provided, making failures loud.
    """

    def __init__(
        self, steps: list[TextStep | ToolCallStep | MultiToolCallStep]
    ) -> None:
        self._steps = list(steps)
        self._call_count = 0
        self._calls: list[dict] = []

    # ── OpenAI client interface ───────────────────────────────────────────────

    @property
    def chat(self) -> "FakeLLMClient":
        return self

    @property
    def completions(self) -> "FakeLLMClient":
        return self

    def create(self, **kwargs: Any) -> _FakeResponse:
        if self._call_count >= len(self._steps):
            raise IndexError(
                f"FakeLLMClient exhausted: {self._call_count} calls made but only "
                f"{len(self._steps)} step(s) configured."
            )
        self._calls.append(kwargs)
        step = self._steps[self._call_count]
        self._call_count += 1
        return _FakeResponse(_step_to_message(step))

    # ── Inspection helpers ────────────────────────────────────────────────────

    @property
    def call_count(self) -> int:
        """Number of create() calls made so far."""
        return self._call_count

    @property
    def calls(self) -> list[dict]:
        """A copy of the kwargs dict captured for each create() call."""
        return list(self._calls)

    def was_exhausted(self) -> bool:
        """True when every scripted step was consumed."""
        return self._call_count == len(self._steps)
