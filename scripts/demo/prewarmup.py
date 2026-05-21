"""Pre-warmup script to run 5-10 minutes before the ELH demo.

What it does:
1. Loads the embedder (5-10 s on cold start) so it stays in RAM.
2. Builds the AgentContext (loads KB + Pinecone client + DB pool).
3. Runs one dummy query through run_agent_turn to:
   - Warm the Anthropic prompt cache (the system prompt is cached
     for 5 minutes after first send, giving ~90% input-token discount
     on subsequent calls).
   - Open and warm the Pinecone HTTPS connection.
   - Open the database connection pool.

After running this script successfully, leave the terminal open
(don't exit). When the actual demo starts within the next 5 minutes,
the first real query will hit a fully-warm cache and return in ~5 s
instead of ~12 s.

Run from the repository root:

    python -m scripts.demo.prewarmup
"""

from __future__ import annotations

import logging
import sys
import time

from elh_rag.agent import AgentContext, run_agent_turn

# Reduce log noise
logging.basicConfig(level=logging.WARNING, format="%(message)s")
for noisy in (
    "elh_rag.agent.loop",
    "elh_rag.agent.agent_llm_client",
    "elh_rag.indexing.embeddings",
    "elh_rag.indexing.pinecone_store",
    "elh_rag.tools",
):
    logging.getLogger(noisy).setLevel(logging.WARNING)


_WARMUP_QUERY = "What is included in the monthly rent?"


def main() -> int:
    print("=" * 60)
    print("ELH Demo — Pre-warmup")
    print("=" * 60)

    print("\n[1/3] Loading embedder + building AgentContext...")
    t0 = time.perf_counter()
    ctx = AgentContext.build()
    print(f"      done in {time.perf_counter() - t0:.1f} s")

    print(f'\n[2/3] Running warmup query: "{_WARMUP_QUERY}"')
    print("      (this seeds the Anthropic prompt cache, ~5 min TTL)")
    t0 = time.perf_counter()
    response = run_agent_turn(query=_WARMUP_QUERY, ctx=ctx)
    print(f"      done in {time.perf_counter() - t0:.1f} s")
    print(f"      tools used: {[t.name for t in response.tool_trace]}")
    print(f"      tokens: {response.input_tokens}in / {response.output_tokens}out")

    print("\n[3/3] Pre-warmup complete.")
    print("\n" + "=" * 60)
    print("  System is ready. The first real demo query will benefit")
    print("  from the warm prompt cache (90% input-token discount)")
    print("  and warm Pinecone / DB connections.")
    print()
    print("  IMPORTANT: do NOT close this terminal or wait too long.")
    print("  The Anthropic prompt cache TTL is 5 minutes. Start the")
    print("  demo within that window for the latency benefit.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
