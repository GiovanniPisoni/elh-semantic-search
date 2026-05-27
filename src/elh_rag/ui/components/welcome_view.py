"""
Welcome view: the first screen the user sees.

Centred logo + title + subtitle, search input, and a 2x2 grid of
quick-question chips. Clicking a chip submits that question directly.
"""

from __future__ import annotations

import streamlit as st

_QUICK_QUESTIONS: list[str] = [
    "Find rooms in Lisbon available from September 2026",
    "What is the cancellation policy and deposit refund?",
    "What is the total cost for a 6-month stay in Intendente?",
    "What do students say about how quiet Alfama is at night?",
]

_LOGO_SVG = """\
<svg width="38" height="38" viewBox="0 0 24 24" fill="none">
  <path d="M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V15H9V21H4C3.45 21 3 20.55 3 20V10.5Z"
        stroke="#1D4ED8" stroke-width="2" stroke-linejoin="round" fill="none"/>
</svg>"""


def render() -> tuple[bool, str]:
    """Render the welcome view. Returns ``(submitted, question)``."""
    st.markdown('<div class="welcome-spacer"></div>', unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        st.markdown(
            f"""
<div class="welcome-brand">
  <div class="welcome-logo">{_LOGO_SVG}</div>
  <h1 class="welcome-title">Welcome to ErASKmus</h1>
  <p class="welcome-subtitle">Your AI assistant for finding student housing in Lisbon and Porto</p>
</div>
""",
            unsafe_allow_html=True,
        )

        with st.form(key="welcome_form", clear_on_submit=False):
            q_col, btn_col = st.columns([9, 1])
            with q_col:
                question = st.text_input(
                    "question",
                    placeholder="Ask anything about ELH housing...",
                    label_visibility="collapsed",
                )
            with btn_col:
                submitted = st.form_submit_button("➤", type="primary", use_container_width=True)

        st.markdown(
            '<p class="welcome-chips-label">Or try one of these questions:</p>',
            unsafe_allow_html=True,
        )

        col_left, col_right = st.columns(2, gap="medium")
        for idx, suggestion in enumerate(_QUICK_QUESTIONS):
            target = col_left if idx % 2 == 0 else col_right
            with target:
                if st.button(suggestion, key=f"qq_{idx}", use_container_width=True):
                    return True, suggestion

    return submitted, question
