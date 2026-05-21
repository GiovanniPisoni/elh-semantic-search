"""Live demo script for the ELH meeting (2026-05-27).

Two parts:

1. Five scripted queries that exercise the three families of tools
   (structured DB, knowledge base, semantic search) plus one common
   sales-style availability query. Each waits for Enter so the
   presenter can comment between them.

2. An open-ended interactive section where audience members can
   type their own questions. The loop continues until the user
   answers 'n' to "Another question?", so the audience can ask as
   many as they want. Errors are caught and shown, but do not stop
   the loop — the system remains usable even if a query is
   malformed.

Output is streamed live; a summary block is shown for each query
(tools used, hops, tokens, latency), and aggregate summaries are
shown after each part.

Run from the repository root:

    python -m scripts.demo.demo_meeting
"""

from __future__ import annotations

import logging
import sys

from elh_rag.agent import AgentContext, run_agent_turn
from elh_rag.agent._models import AgentResponse, ToolCall

# Reduce log noise so the presenter sees a clean output
logging.basicConfig(level=logging.WARNING, format="%(message)s")
# Silence specific noisy loggers
for noisy in (
    "elh_rag.agent.loop",
    "elh_rag.agent.agent_llm_client",
    "elh_rag.indexing.embeddings",
    "elh_rag.indexing.pinecone_store",
    "elh_rag.tools",
):
    logging.getLogger(noisy).setLevel(logging.WARNING)


_QUERIES: list[tuple[str, str, str]] = [
    (
        "Q1 — Structural filter",
        "Find the cheapest single rooms in Lisbon under 450 EUR",
        "Catalogue filtering with constraints. Pure SQL territory.",
    ),
    (
        "Q2 — Availability for a period (sales-style)",
        "Which rooms are available in Lisbon for September 2026?",
        "A question the sales team asks every day. Checks availability across the inventory.",
    ),
    (
        "Q3 — Policy",
        "What is included in the monthly rent?",
        "Knowledge-base lookup. The agent uses a curated KB of 27 policy entries.",
    ),
    (
        "Q4 — Multi-hop reasoning",
        (
            "Total cost for a 6-month stay in the cheapest available room "
            "in Lisbon from September 2026"
        ),
        "Two tools chained automatically: find_available_rooms then compute_total_cost. No router.",
    ),
    (
        "Q5 — Semantic search on reviews",
        "Is the Alfama neighborhood quiet at night?",
        "Pure subjective question, only answerable from past student reviews.",
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
    print(f"  Query: {query}")
    print(f"  ({hint})")
    print(_SEPARATOR)


def _print_text_delta(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _print_tool_call(tc: ToolCall) -> None:
    print()  # newline after streamed text
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


def _run_interactive(ctx: AgentContext) -> dict[str, int]:
    """Open-ended Q&A loop until the user types N.

    Returns aggregate stats (count, input_tokens, output_tokens,
    duration_ms) so the caller can include them in the final summary.
    Errors from run_agent_turn are caught and printed but do not stop
    the loop — this keeps the demo flowing if a query is malformed
    or hits a backend hiccup.
    """
    print(f"\n{_SEPARATOR}")
    print("INTERACTIVE — now it's your turn")
    print(_SEPARATOR)
    print("  Type any question you want, in any of the 6 supported languages.")
    print("  Press Enter on an empty line to skip; type 'n' at the prompt to end.")

    count = 0
    total_input = 0
    total_output = 0
    total_duration = 0

    while True:
        count += 1
        print(f"\n{_SEPARATOR}")
        print(f"Interactive Q{count}")
        print(_THIN_SEP)

        try:
            query = input("Your question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  (interrupted)")
            break

        if not query:
            print("  (empty input, skipping)")
            count -= 1
            continue

        print(_THIN_SEP)
        try:
            response = run_agent_turn(
                query=query,
                ctx=ctx,
                on_text=_print_text_delta,
                on_tool_call=_print_tool_call,
            )
            _print_summary(response)
            total_input += response.input_tokens
            total_output += response.output_tokens
            total_duration += response.total_duration_ms
        except Exception as exc:
            # Don't crash the demo on a backend error — surface it and continue
            print(f"\n  [error] {type(exc).__name__}: {exc}")
            print("  (the system rejected this input — feel free to try another question)")
            count -= 1

        # Ask if they want another one
        try:
            again = input("\n  Another question? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  (interrupted)")
            break

        if again in ("n", "no", "exit", "quit"):
            break
        # Any other input (including empty) -> continue

    return {
        "count": count,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "duration_ms": total_duration,
    }


def main() -> int:
    print(_SEPARATOR)
    print("ELH AI Assistant — Phase 3 Live Demo")
    print(_SEPARATOR)
    print("\nBuilding agent context (loads embedder, ~3 s)...")

    ctx = AgentContext.build()

    print("Ready. Press Enter to start each query.")
    _press_enter("\n  (press Enter to start Q1)")

    total = len(_QUERIES)
    total_input_tokens = 0
    total_output_tokens = 0
    total_duration_ms = 0

    for idx, (title, query, hint) in enumerate(_QUERIES, start=1):
        _print_section_header(idx, total, title, query, hint)

        response = run_agent_turn(
            query=query,
            ctx=ctx,
            on_text=_print_text_delta,
            on_tool_call=_print_tool_call,
        )
        _print_summary(response)

        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens
        total_duration_ms += response.total_duration_ms

        if idx < total:
            _press_enter(f"\n  (press Enter to start Q{idx + 1})")

    # Aggregate summary for the 5 scripted queries
    print(f"\n{_SEPARATOR}")
    print("SCRIPTED DEMO COMPLETE")
    print(_SEPARATOR)
    print(
        f"  queries: {total}  |  "
        f"total tokens: {total_input_tokens}in / {total_output_tokens}out  |  "
        f"total time: {total_duration_ms / 1000:.1f}s"
    )

    # Open-ended interactive section
    interactive = _run_interactive(ctx)

    if interactive["count"] > 0:
        print(f"\n{_SEPARATOR}")
        print("INTERACTIVE PART COMPLETE")
        print(_SEPARATOR)
        print(
            f"  queries: {interactive['count']}  |  "
            f"total tokens: {interactive['input_tokens']}in / "
            f"{interactive['output_tokens']}out  |  "
            f"total time: {interactive['duration_ms'] / 1000:.1f}s"
        )

    print(f"\n{_SEPARATOR}")
    print("End of demo. Thanks!")
    print(_SEPARATOR)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
