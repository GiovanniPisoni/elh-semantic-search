"""
Results panel (right column of the chat view).

Shows a header with the property count, followed by a scrollable list of
property cards — one card per retrieval source.
"""
from __future__ import annotations

import streamlit as st

from elh_rag.schemas import RAGResponse
from elh_rag.ui.components import property_card


def render(response: RAGResponse) -> None:
    """Render the results panel for the given RAG response."""
    sources = response.sources
    cards_html = "".join(property_card.render(src) for src in sources)

    sub_label = _build_sub_label(response)

    st.markdown(
        f"""
<div class="chat-right-root">
  <div class="chat-right-header">
    <div class="chat-right-header-title">Results found</div>
    <div class="chat-right-header-sub">{sub_label}</div>
  </div>
  <div class="chat-right-cards">
    {cards_html}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    _render_debug_expander(response)


def _build_sub_label(response: RAGResponse) -> str:
    """Build the header subtitle: total count + per-source breakdown if mixed."""
    total = len(response.sources)
    by_source = response.sources_by_source

    if not by_source or len(by_source) <= 1:
        # Single corpus or no per-source info — keep the original label
        return f"{total} properties"

    # Mixed corpora → show breakdown
    chunks: list[str] = []
    for corpus_name, items in by_source.items():
        if items:
            chunks.append(f"{len(items)} {corpus_name}")
    if not chunks:
        return f"{total} properties"
    return f"{total} sources · " + ", ".join(chunks)


def _render_debug_expander(response: RAGResponse) -> None:
    """Show routing/rewrite info inside a collapsed expander."""
    routing = response.routing
    rewritten = response.rewritten_query

    if routing is None and rewritten is None:
        return

    with st.expander("⚙︎ How was this answered? (debug)", expanded=False):
        if routing is not None:
            st.markdown(
                f"**Routing intent:** `{routing.intent.value}`  "
                f"·  **Confidence:** {routing.confidence:.2f}  "
                f"·  **Source:** `{routing.source}`"
            )
            if routing.reasoning:
                st.markdown(f"_{routing.reasoning}_")

        if rewritten:
            st.markdown(f"**Rewritten query:** *{rewritten}*")

        st.markdown(f"**Pipeline mode:** `{response.mode}`")