"""End-to-end smoke test of conversation memory against live services.

Simulates a 3-turn conversation where each turn depends on context
from the previous one:

    Turn 1: "Find the cheapest single rooms in Lisbon."
            -> agent returns a list of rooms

    Turn 2: "What's the total cost for 6 months from September for
            the cheapest one?"
            -> agent must resolve "the cheapest one" by reading the
               assistant's prior reply

    Turn 3: "What about the second one?"
            -> agent must resolve "the second one" by reading two
               turns back

After each turn, the script prints the agent's final_message and
records it as the assistant turn for the next call. A final summary
prints aggregate token usage and the elapsed time.

Estimated cost per full run: ~$0.05. Manual execution only.
"""

from __future__ import annotations

import logging
import sys

from elh_rag.agent import AgentContext, ConversationTurn, run_agent_turn
from elh_rag.agent._models import AgentResponse, ToolCall
from elh_rag.logging_setup import setup_logging

logger = logging.getLogger(__name__)


_TURNS: list[str] = [
    "Find the cheapest single rooms in Lisbon.",
    ("What's the total cost for 6 months from September 2026 for the cheapest one?"),
    "And the second one in your list?",
]


_SEPARATOR = "=" * 72


def _print_section_header(turn_idx: int, query: str) -> None:
    print(f"\n{_SEPARATOR}")
    print(f"Turn {turn_idx} (user)")
    print(f"  > {query}")
    print(_SEPARATOR)


def _print_text_delta(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _print_tool_call(tc: ToolCall) -> None:
    print()
    truncated = tc.input_json[:120]
    if len(tc.input_json) > 120:
        truncated += "..."
    status = "ERROR" if tc.error else "OK"
    print(f"  [tool {tc.hop_index} {status} {tc.duration_ms}ms] {tc.name}({truncated})")
    if tc.error:
        print(f"    error: {tc.error}")


def _print_summary(idx: int, response: AgentResponse) -> None:
    tools = [t.name for t in response.tool_trace]
    print()
    print(
        f"\n[Turn {idx} summary]  "
        f"stop_reason={response.stop_reason}  "
        f"hops={response.hop_count}  "
        f"tools={tools}  "
        f"tokens={response.input_tokens}in/{response.output_tokens}out  "
        f"duration={response.total_duration_ms}ms"
    )


def main() -> int:
    setup_logging()
    logger.info("smoke_test_conversation: starting (%d turns)", len(_TURNS))

    print("\nBuilding AgentContext...")
    ctx = AgentContext.build()
    print("AgentContext ready.")

    history: list[ConversationTurn] = []
    total_input = 0
    total_output = 0
    total_duration = 0
    failures: list[str] = []

    for idx, query in enumerate(_TURNS, start=1):
        _print_section_header(idx, query)
        try:
            response = run_agent_turn(
                query=query,
                ctx=ctx,
                on_text=_print_text_delta,
                on_tool_call=_print_tool_call,
                conversation_history=history if history else None,
            )
            _print_summary(idx, response)

            # Record this turn into the history for the next call.
            history.append(ConversationTurn(role="user", content=query))
            history.append(
                ConversationTurn(
                    role="assistant",
                    content=response.final_message,
                )
            )

            total_input += response.input_tokens
            total_output += response.output_tokens
            total_duration += response.total_duration_ms

        except Exception as exc:
            print(f"\n[Turn {idx} FAILED] {type(exc).__name__}: {exc}")
            logger.exception("turn %d failed", idx)
            failures.append(f"turn {idx}: {exc}")

    print(f"\n{_SEPARATOR}")
    print("CONVERSATION COMPLETE")
    print(_SEPARATOR)
    print(f"Turns:    {len(_TURNS)} ({len(failures)} failed)")
    print(f"Tokens:   {total_input} in / {total_output} out")
    print(f"Duration: {total_duration / 1000:.1f}s total")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
