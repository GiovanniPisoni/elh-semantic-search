"""
Results panel (right column of the chat view).

Shows a header with the property count, followed by a scrollable list of
property cards — one card per retrieval source.
"""
from __future__ import annotations

import streamlit as st

from elh_rag.schemas import RetrievalResult
from elh_rag.ui.components import property_card


def render(sources: list[RetrievalResult]) -> None:
    """Render the results panel for the given retrieval sources."""
    cards_html = "".join(property_card.render(src) for src in sources)

    st.markdown(
        f"""
<div class="chat-right-root">
  <div class="chat-right-header">
    <div class="chat-right-header-title">Results found</div>
    <div class="chat-right-header-sub">{len(sources)} properties</div>
  </div>
  <div class="chat-right-cards">
    {cards_html}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
