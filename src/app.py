import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline import query as rag_query

st.set_page_config(
    page_title="ELH semantic search",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .answer-box {
        background-color: #1a2535;
        border-left: 4px solid #4a90d9;
        padding: 1.2rem 1.5rem;
        border-radius: 0 8px 8px 0;
        margin-bottom: 1.5rem;
        font-size: 0.97rem;
        line-height: 1.8;
        color: #e8edf5;
    }
    .source-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.6rem;
    }
    .score-badge {
        display: inline-block;
        background-color: #2E5FA3;
        color: white;
        border-radius: 12px;
        padding: 2px 10px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .score-low {
        background-color: #999;
    }
    .meta-tag {
        display: inline-block;
        background-color: #eef2f7;
        color: #2E5FA3;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.75rem;
        margin-right: 4px;
        margin-bottom: 4px;
    }
    .star-rating {
        color: #f5a623;
        font-size: 0.9rem;
    }
    .history-item {
        border-left: 3px solid #ddd;
        padding-left: 0.7rem;
        margin-bottom: 0.4rem;
        font-size: 0.85rem;
        color: #555;
        cursor: pointer;
    }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://img.icons8.com/color/96/home--v2.png", width=60)
    st.title("ELH semantic search")
    st.caption("RAG-based search on student reviews · Thesis Project 2026-2027")

    st.divider()

    st.subheader("Search settings")

    top_k = st.slider(
        "Number of reviews to retrieve",
        min_value=3, max_value=10, value=5,
        help="How many reviews ChromaDB retrives before passing them to Claude."
    )

    city_filter = st.selectbox(
        "Filter by city",
        options=["All cities", "Lisbon", "Porto"],
        index=0
    )
    city_filter = None if city_filter == "All cities" else city_filter

    min_rating = st.select_slider(
        "Minimum overall rating",
        options=[1, 2, 3, 4, 5],
        value=1,
        format_func=lambda x: f"{'⭐' * x} ({x}/5)"
    )
    min_rating = None if min_rating == 1 else min_rating

    st.divider()

    st.subheader("Example questions")
    example_questions = [
        "Find rooms where students mention a comfortable bed",
        "Which landlords are described as responsive?",
        "Properties with fast WiFi for studying",
        "Are there complaints about cleanliness?",
        "Apartments with sea or city views",
        "Rooms suitable for students who study late",
        "Properties with good location and transport links",
        "Rooms with private bathroom praised by students",
    ]
    
    for eq in example_questions:
        if st.button(eq, key=f"ex_{eq[:20]}", use_container_width=True):
            st.session_state["prefill_question"] = eq
            st.session_state["auto_search"] = True
            st.rerun()

    st.divider()
    st.caption("Alma Mater Studiorum · Università di Bologna · 2026/2027")
    st.caption("System: Naive RAG · Model: paraphrase-multilingual-mpnet-base-v2 · LLM: Claude")

st.title("ELH semantic search")
st.markdown(
    "Ask anything about Erasmus Life Housing properties in **natural language**. "
    "The system searches across **all the real student reviews** and generates a "
    "grounded answer citing the relevant sources."
)
st.divider()

if "history" not in st.session_state:
    st.session_state["history"] = []
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
if "prefill_question" not in st.session_state:
    st.session_state["prefill_question"] = ""
if "auto_search" not in st.session_state:
    st.session_state["auto_search"] = False

col_input, col_btn = st.columns([5, 1])

with st.form(key="search_form", clear_on_submit=False):
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        question = st.text_input(
            "Your question",
            value=st.session_state.get("prefill_question", ""),
            placeholder="e.g. Find rooms where students mention a comfortable bed...",
            label_visibility="collapsed",
        )
    with col_btn:
        search_clicked = st.form_submit_button(
            "🔍 Search", type="primary", use_container_width=True
        )

if st.session_state.get("prefill_question"):
    st.session_state["prefill_question"] = ""

if st.session_state.get("auto_search"):
    st.session_state["auto_search"] = False
    search_clicked = True

if search_clicked and question.strip():
    with st.spinner("Searching reviews and generating answer..."):
        result = rag_query(
            question=question.strip(),
            top_k=top_k,
            city_filter=city_filter,
            min_rating=min_rating,
        )

        st.session_state["last_result"] = result
        history = st.session_state["history"]
        if question not in [h["q"] for h in history]:
            history.insert(0, {"q": question, "n_sources": len(result["sources"])})
        st.session_state["history"] = history[:10]

elif search_clicked and not question.strip():
    st.warning("Please enter a question before searching.")

result = st.session_state.get("last_result")

if result:
    st.subheader("💬 Answer")
    st.markdown(
        f'<div class="answer-box">{result["answer"]}</div>',
        unsafe_allow_html=True
    )
 
    sources = result["sources"]
    if sources:
        st.subheader(f"📚 Sources — {len(sources)} reviews retrieved")
 
        for i, src in enumerate(sources, 1):
            meta  = src["metadata"]
            score = src.get("score", 0)
 
            city      = meta.get("city", "")
            zone      = meta.get("zone", "")
            flatname  = meta.get("flatname", "")
            roomname  = meta.get("roomname", "")
            rating    = meta.get("overall_rating", 0)
            title     = meta.get("review_title", "")
            orig_text = meta.get("review_text_original", src["text"])
 
            # Badge score colorato in base alla rilevanza
            score_pct = int(score * 100)
            badge_cls = "score-badge" if score >= 0.5 else "score-badge score-low"
            stars     = "⭐" * int(rating) if rating else ""
 
            location_str = ", ".join(filter(None, [zone, city]))
            property_str = " — ".join(filter(None, [flatname, roomname]))
 
            with st.expander(
                f"[{i}] {location_str}  ·  {flatname}  "
                f"{'⭐' * int(rating) if rating else ''}  "
                f"· Similarity: {score:.3f}",
                expanded=(i == 1),
            ):
                # Metadati
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f"**📍 Location**")
                    st.markdown(f"{zone}, {city}")
                with col_b:
                    st.markdown(f"**🏠 Property**")
                    st.markdown(property_str or "—")
                with col_c:
                    st.markdown(f"**⭐ Rating**")
                    st.markdown(f"{rating}/5  {stars}")
 
                st.divider()
 
                if title:
                    st.markdown(f"**\"{title}\"**")
                st.markdown(orig_text)
 
                st.caption(f"Similarity score: {score:.4f} · ID: {meta.get('id', '—')}")
 
    else:
        st.info("No relevant reviews found for your question. Try rephrasing or removing filters.")
 
    if sources:
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        avg_score  = sum(s["score"] for s in sources) / len(sources)
        avg_rating = sum(s["metadata"].get("overall_rating", 0) for s in sources) / len(sources)
        cities     = set(s["metadata"].get("city", "") for s in sources)
 
        m1.metric("Reviews retrieved", len(sources))
        m2.metric("Avg similarity", f"{avg_score:.3f}")
        m3.metric("Avg rating of sources", f"{avg_rating:.1f}/5")
        m4.metric("Cities covered", ", ".join(filter(None, cities)))

if st.session_state["history"] and len(st.session_state["history"]) > 1:
    st.divider()
    st.subheader("recent searches")
    for item in st.session_state["history"][1:]:
        col_h, col_n = st.columns([6, 1])
        with col_h:
            if st.button(
                f"↩ {item['q']}",
                key=f"hist_{item['q'][:30]}",
                use_container_width=True,
            ):
                st.session_state["prefill_question"] = item["q"]
                st.rerun()
        with col_n:
            st.caption(f"{item['n_sources']} src")

if not result and not search_clicked:
    st.markdown("""
    <div style="text-align:center; padding: 3rem 2rem; color: #888;">
        <div style="font-size: 3rem;">🔍</div>
        <div style="font-size: 1.1rem; margin-top: 1rem;">
            Type a question above or choose one from the sidebar to get started.
        </div>
        <div style="font-size: 0.9rem; margin-top: 0.5rem;">
            The system searches student reviews from Lisbon and Porto
            and generates a grounded answer using Claude AI.
        </div>
    </div>
    """, unsafe_allow_html=True)