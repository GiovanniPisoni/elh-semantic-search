"""
Welcome view: the first screen the user sees (mockup #1).

Centred logo + title, search input, and a 2×2 grid of suggestion chips.
Clicking a chip pre-fills the input and auto-submits on the next rerun.
"""
from __future__ import annotations

import streamlit as st

from elh_rag.ui import state


_SUGGESTIONS: list[str] = [
    "Rooms with a comfortable bed",
    "Fast WiFi for studying",
    "Near metro or public transport",
    "Responsive and helpful landlords",
]

_LOGO_SVG = """\
<svg width="38" height="38" viewBox="0 0 24 24" fill="none">
  <path d="M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V15H9V21H4C3.45 21 3 20.55 3 20V10.5Z"
        stroke="#1D4ED8" stroke-width="2" stroke-linejoin="round" fill="none"/>
</svg>"""


def render() -> tuple[bool, str, st.delta_generator.DeltaGenerator]:
    """Render the welcome view.

    Returns:
        (submitted, question, loading_slot)
        - submitted:    True if the user submitted the form or a chip
        - question:     the (possibly empty) question text
        - loading_slot: empty st.empty() slot where loaders can be rendered
    """
    st.markdown('<div class="welcome-spacer"></div>', unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        st.markdown(
            f"""
<div class="welcome-brand">
  <div class="welcome-logo">{_LOGO_SVG}</div>
  <h1 class="welcome-title">Welcome in ErASKmus</h1>
  <p class="welcome-subtitle">Your ELH AI — find the perfect room in Lisbon &amp; Porto</p>
</div>
""",
            unsafe_allow_html=True,
        )

        loading_slot = st.empty()

        with st.form(key="welcome_form", clear_on_submit=False):
            q_col, btn_col = st.columns([9, 1])
            with q_col:
                question = st.text_input(
                    "question",
                    value=state.consume_prefill(),
                    placeholder="Describe your ideal room...",
                    label_visibility="collapsed",
                )
            with btn_col:
                submitted = st.form_submit_button(
                    "➤", type="primary", use_container_width=True
                )

        if state.consume_auto_submit():
            submitted = True

        st.markdown(
            '<p class="welcome-chips-label">Or try one of these questions:</p>',
            unsafe_allow_html=True,
        )

        col_left, col_right = st.columns(2, gap="medium")
        for idx, suggestion in enumerate(_SUGGESTIONS):
            target = col_left if idx % 2 == 0 else col_right
            with target:
                if st.button(
                    suggestion, key=f"sug_{idx}", use_container_width=True
                ):
                    state.set_prefill(suggestion, auto_submit=True)
                    st.rerun()

    return submitted, question, loading_slot
