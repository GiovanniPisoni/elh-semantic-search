"""End-to-end smoke test of the Phase 3 agent loop against live services.

Runs five canonical queries that together exercise the three families
of tools (structured DB, knowledge base, semantic search) plus a
multi-hop chain and a multilingual query.

Each query prints the streaming text + per-tool trace as it happens,
then a summary block with stop_reason, hop count, tool list, and
token usage.
"""

from __future__ import annotations

import logging
import sys

from elh_rag.agent import AgentContext, run_agent_turn
from elh_rag.agent._models import AgentResponse, ToolCall
from elh_rag.logging_setup import setup_logging

logger = logging.getLogger(__name__)


_QUERIES: list[tuple[str, str]] = [
    ("EN structural", "Find the cheapest single rooms in Lisbon"),
    ("IT policy", "Quanto costa la cauzione?"),
    ("EN dates", "Show me rooms available in Porto for September 2026"),
    (
        "EN multi-hop",
        "Find the cheapest room in Lisbon and tell me the total cost for 6 months from September 2026",
    ),
    ("EN semantic", "Is the Alfama neighborhood quiet at night?"),
]


_SEPARATOR = "=" * 72


def _print_section_header(label: str, query: str) -> None:
    print(f"\n{_SEPARATOR}")
    print(f"Query [{label}]")
    print(f"  > {query}")
    print(_SEPARATOR)


def _print_text_delta(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _print_tool_call(tc: ToolCall) -> None:
    print()  # newline after any streamed text
    truncated_input = tc.input_json[:120]
    if len(tc.input_json) > 120:
        truncated_input += "..."
    status = "ERROR" if tc.error else "OK"
    print(f"  [tool {tc.hop_index} {status} {tc.duration_ms}ms] {tc.name}({truncated_input})")
    if tc.error:
        print(f"    error: {tc.error}")


def _print_summary(response: AgentResponse) -> None:
    tools = [t.name for t in response.tool_trace]
    print()
    print(
        f"\nstop_reason={response.stop_reason}  "
        f"hops={response.hop_count}  "
        f"tools={tools}  "
        f"tokens={response.input_tokens}in/{response.output_tokens}out  "
        f"duration={response.total_duration_ms}ms"
    )


def main() -> int:
    setup_logging()
    logger.info("smoke_test_agent: starting (%d queries)", len(_QUERIES))

    print("\nBuilding AgentContext (this loads the embedder, ~2-4 s)...")
    ctx = AgentContext.build()
    print("AgentContext ready.")

    total_input_tokens = 0
    total_output_tokens = 0
    total_duration_ms = 0
    failures: list[str] = []

    for label, query in _QUERIES:
        _print_section_header(label, query)
        try:
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
        except Exception as exc:
            print(f"\n[FAILED] {type(exc).__name__}: {exc}")
            failures.append(f"{label}: {type(exc).__name__}")
            logger.exception("smoke_test_agent: query %r failed", label)

    print(f"\n{_SEPARATOR}")
    print(
        f"TOTAL  tokens={total_input_tokens}in/{total_output_tokens}out  "
        f"duration={total_duration_ms}ms  "
        f"failures={len(failures)}/{len(_QUERIES)}"
    )
    if failures:
        for f in failures:
            print(f"  FAILED: {f}")
        return 1
    print("All queries succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
