"""
SleepCal agent — terminal REPL entry point.

Usage:
    uv run python agent/main.py
"""

from __future__ import annotations

import json
import os
import readline  # noqa: F401  — activates line-editing / history for input()
import sys
from pathlib import Path

# Ensure the project root is on sys.path so absolute imports work whether
# this file is run as `python agent/main.py` or `python -m agent.main`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env before importing anything that reads env vars.
from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from openai import OpenAI  # noqa: E402  (import after dotenv)

from agent.system_prompt import get_system_prompt  # noqa: E402
from agent.tools import TOOLS, dispatch  # noqa: E402

# ---------------------------------------------------------------------------
# User preference helpers
# ---------------------------------------------------------------------------

_PREFS_PATH = Path(__file__).parent.parent / "user-prefs.json"


def _load_prefs() -> dict:
    try:
        with open(_PREFS_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _prefs_note(prefs: dict) -> str:
    if not prefs:
        return ""
    return (
        f"\n[User sleep preferences — bedtime: {prefs.get('bedtime', 'unknown')}, "
        f"waketime: {prefs.get('waketime', 'unknown')}, "
        f"wind-down: {prefs.get('wind_down_mins', '?')} mins]"
    )


# ---------------------------------------------------------------------------
# OpenAI client (pointing at OpenRouter)
# ---------------------------------------------------------------------------


def _make_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("ERROR: OPENROUTER_API_KEY is not set in the environment / .env file.")
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )


MODEL = "google/gemini-3.5-flash"

# ---------------------------------------------------------------------------
# Agent step: single LLM + tool loop iteration
# ---------------------------------------------------------------------------


def _run_turn(client: OpenAI, messages: list[dict]) -> str:
    """
    Send messages to the LLM and handle any tool calls until the model
    returns a final text response. Returns the assistant's reply string.
    """
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,  # type: ignore[arg-type]
            tool_choice="auto",
        )

        message = response.choices[0].message

        # Append the raw assistant message (may contain tool_calls).
        messages.append(message.model_dump(exclude_unset=False))

        # If no tool calls, we have the final answer.
        if not message.tool_calls:
            return message.content or ""

        # Execute every tool call and append results.
        for tc in message.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            print(
                f"  [tool] {fn_name}({json.dumps(fn_args, separators=(',', ':'))})",
                flush=True,
            )
            result = dispatch(fn_name, fn_args)
            print(
                f"  [tool result] {result[:200]}{'…' if len(result) > 200 else ''}",
                flush=True,
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

BANNER = """\
╔══════════════════════════════════════════╗
║          SleepCal Agent  💤              ║
║  Type your request, or 'exit' to quit.   ║
╚══════════════════════════════════════════╝"""


def main() -> None:
    prefs = _load_prefs()
    client = _make_client()

    system_content = get_system_prompt()
    if prefs:
        system_content += _prefs_note(prefs)

    messages: list[dict] = [{"role": "system", "content": system_content}]

    print(BANNER)
    if prefs:
        print(
            f"  Sleep prefs loaded → bedtime {prefs.get('bedtime')}, "
            f"wake {prefs.get('waketime')}, "
            f"wind-down {prefs.get('wind_down_mins')} mins\n"
        )

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodnight! 🌙")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "bye"}:
            print("Goodnight! 🌙")
            break

        messages.append({"role": "user", "content": user_input})

        try:
            reply = _run_turn(client, messages)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {exc}")
            # Remove the user turn so the conversation stays consistent.
            messages.pop()
            continue

        print(f"\nSleepCal: {reply}\n")


if __name__ == "__main__":
    main()
