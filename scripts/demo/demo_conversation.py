"""Conversation memory demo for the ELH meeting (2026-05-27).

Simulates a 3-turn conversation that demonstrates the agent's
ability to resolve anaphoric references ("the cheapest one", "the
second one") by reading the prior assistant reply.

Each turn waits for the user to press Enter before running. The
history is accumulated client-side and passed to run_agent_turn on
each call.

Run from the repository root:

    python -m scripts.demo.demo_conversation
"""

from __future__ import annotations

import logging
import sys

from elh_rag.agent import AgentContext, ConversationTurn, run_agent_turn
from elh_rag.agent._models import AgentResponse, ToolCall

# Reduce log noise so the presenter sees a clean output
logging.basicConfig(level=logging.WARNING, format="%(message)s")
for noisy in (
    "elh_rag.agent.loop",
    "elh_rag.agent.agent_llm_client",
    "elh_rag.indexing.embeddings",
    "elh_rag.indexing.pinecone_store",
    "elh_rag.tools",
):
    logging.getLogger(noisy).setLevel(logging.WARNING)


_TURNS: list[tuple[str, str, str]] = [
    (
        "Turn 1 — Open-ended catalogue query",
        "Find the cheapest single rooms in Lisbon.",
        "The user asks a normal question. The agent answers with a list.",
    ),
    (
        "Turn 2 — Anaphoric reference: 'the cheapest one'",
        "What's the total cost for 6 months from September 2026 for the cheapest one?",
        "Notice: no room ID, no name. The agent must read Turn 1's reply to know which room.",
    ),
    (
        "Turn 3 — Ordinal reference: 'the second one'",
        "And the second one in your list?",
        "Still no name. The agent walks two turns back to find the right room.",
    ),
]


_SEPARATOR = "=" * 78
_THIN_SEP = "-" * 78


def _press_enter(prompt: str = "  (press Enter to continue)") -> None:
    try:
        input(prompt)
    except (EOFError, KeyboardInterrupt):
        print("\nDemo interrupted by user.")
        sys.exit(0)


def _print_section_header(idx: int, total: int, title: str, query: str, hint: str) -> None:
    print(f"\n{_SEPARATOR}")
    print(f"[{idx}/{total}] {title}")
    print(_THIN_SEP)
    print(f"  User: {query}")
    print(f"  ({hint})")
    print(_SEPARATOR)


def _print_text_delta(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _print_tool_call(tc: ToolCall) -> None:
    print()
    truncated = tc.input_json[:100]
    if len(tc.input_json) > 100:
        truncated += "..."
    status = "OK" if tc.error is None else "ERROR"
    print(f"  -> [tool {tc.hop_index} {status} {tc.duration_ms} ms] {tc.name}({truncated})")


def _print_summary(response: AgentResponse) -> None:
    tools = [t.name for t in response.tool_trace]
    print()
    print(_THIN_SEP)
    print(
        f"  summary: {response.hop_count} hops, "
        f"tools={tools}, "
        f"tokens={response.input_tokens}in/{response.output_tokens}out, "
        f"latency={response.total_duration_ms / 1000:.1f}s"
    )


def main() -> int:
    print(_SEPARATOR)
    print("ELH AI Assistant — Conversation Memory Demo")
    print(_SEPARATOR)
    print("\nBuilding agent context (loads embedder, ~3 s)...")

    ctx = AgentContext.build()

    print("Ready. Press Enter to start each turn.")
    _press_enter("\n  (press Enter to start Turn 1)")

    history: list[ConversationTurn] = []
    total = len(_TURNS)
    total_input_tokens = 0
    total_output_tokens = 0
    total_duration_ms = 0

    for idx, (title, query, hint) in enumerate(_TURNS, start=1):
        _print_section_header(idx, total, title, query, hint)

        response = run_agent_turn(
            query=query,
            ctx=ctx,
            on_text=_print_text_delta,
            on_tool_call=_print_tool_call,
            conversation_history=history if history else None,
        )
        _print_summary(response)

        # Append this turn to the history for the next call
        history.append(ConversationTurn(role="user", content=query))
        history.append(ConversationTurn(role="assistant", content=response.final_message))

        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens
        total_duration_ms += response.total_duration_ms

        if idx < total:
            _press_enter(f"\n  (press Enter to start Turn {idx + 1})")

    # Aggregate summary
    print(f"\n{_SEPARATOR}")
    print("CONVERSATION COMPLETE")
    print(_SEPARATOR)
    print(
        f"  turns: {total}  |  "
        f"history size: {len(history)} entries  |  "
        f"total tokens: {total_input_tokens}in / {total_output_tokens}out  |  "
        f"total time: {total_duration_ms / 1000:.1f}s"
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
