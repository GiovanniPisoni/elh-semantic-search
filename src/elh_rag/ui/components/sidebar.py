"""
Sidebar component: search filters + recent queries.

Collapsed by default (the default welcome view hides it). The user can
expand it to refine retrieval behaviour (top-k, city, min rating) or to
jump back to a previous query.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from elh_rag.ui import state


@dataclass(slots=True)
class SidebarFilters:
    """Filter values selected by the user in the sidebar."""

    top_k: int
    city: str | None
    min_rating: int | None


def render() -> SidebarFilters:
    """Render the sidebar and return the current filter selection."""
    with st.sidebar:
        st.markdown(
            '<p style="font-size:.75rem;font-weight:700;color:#64748B;'
            "text-transform:uppercase;letter-spacing:.07em;margin-bottom:.5rem;\">"
            "Search settings</p>",
            unsafe_allow_html=True,
        )

        top_k = st.slider("Reviews", 3, 10, 5)

        city_choice = st.selectbox("City", ["All cities", "Lisbon", "Porto"])
        city = None if city_choice == "All cities" else city_choice

        min_rating_choice = st.select_slider(
            "Min rating",
            [1, 2, 3, 4, 5],
            1,
            format_func=lambda x: "★" * x + "☆" * (5 - x),
        )
        min_rating = None if min_rating_choice == 1 else min_rating_choice

        recent = state.get_recent_queries()
        if recent:
            st.divider()
            st.markdown("**Recent**")
            for item in recent:
                label = f"↩ {item['q'][:32]}"
                if st.button(label, key=f"sh_{item['q'][:28]}", use_container_width=True):
                    state.set_prefill(item["q"], auto_submit=True)
                    st.rerun()

    return SidebarFilters(top_k=top_k, city=city, min_rating=min_rating)
