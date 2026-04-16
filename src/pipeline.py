import os
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL",
                              "paraphrase-multilingual-mpnet-base-v2")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX   = os.getenv("PINECONE_INDEX_NAME", "elh-reviews")
LLM_MODEL        = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_TEMPERATURE  = float(os.getenv("LLM_TEMPERATURE", "0.1"))
RETRIEVAL_TOP_K  = int(os.getenv("RETRIEVAL_TOP_K", "5"))

SYSTEM_PROMPT = """You are a helpful assistant for Erasmus Life Housing (ELH), \
a student accommodation platform in Lisbon and Porto, Portugal.

Your role is to answer questions about properties and student experiences \
based exclusively on real student reviews provided to you as context.

Rules you must always follow:
- Base your answer ONLY on the reviews provided in the context below.
- If the reviews do not contain enough information to answer the question, \
say so clearly — do not invent or assume anything.
- Always cite which reviews you are drawing from (e.g. "According to a review \
of Casa do Sol in Alfama...").
- Be concise and helpful. Prioritise the most relevant information.
- Respond in the same language as the user's question (English or Portuguese).
"""

USER_PROMPT_TEMPLATE = """Based on the following student reviews, please answer this question:

Question: {question}

---
STUDENT REVIEWS:
{context}
---

Please provide a clear, helpful answer citing the relevant reviews."""

_embedding_model  = None
_pinecone_index   = None
_anthropic_client = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX)
    return _pinecone_index


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
    return _anthropic_client


def retrieve(question: str,
             top_k: int = RETRIEVAL_TOP_K,
             city_filter: str = None,
             min_rating: int = None) -> list[dict]:
    """
    Converte la domanda in embedding e cerca in Pinecone.
    Supporta filtri per città e rating minimo.
    """
    model = _get_embedding_model()
    index = _get_pinecone_index()

    question_embedding = model.encode(
        question,
        normalize_embeddings=True
    ).tolist()

    pinecone_filter = {}
    if city_filter:
        pinecone_filter["city"] = {"$eq": city_filter}
    if min_rating:
        pinecone_filter["overall_rating"] = {"$gte": min_rating}

    query_params = {
        "vector":          question_embedding,
        "top_k":           top_k,
        "include_metadata": True,
    }
    if pinecone_filter:
        query_params["filter"] = pinecone_filter

    results = index.query(**query_params)

    documents = []
    for match in results.matches:
        documents.append({
            "text":     match.metadata.get("review_text_original",
                        match.metadata.get("text", "")),
            "metadata": match.metadata,
            "score":    round(match.score, 3),
            "distance": round(1 - match.score, 3),
        })

    return documents


def build_context(documents: list[dict]) -> str:
    context_parts = []
    for i, doc in enumerate(documents, 1):
        meta     = doc["metadata"]
        city     = meta.get("city", "")
        zone     = meta.get("zone", "")
        flatname = meta.get("flatname", "")
        roomname = meta.get("roomname", "")
        rating   = meta.get("overall_rating", "")
        title    = meta.get("review_title", "")
        text     = meta.get("review_text_original", doc["text"])

        location = ", ".join(filter(None, [zone, city]))
        prop     = " — ".join(filter(None, [flatname, roomname]))

        header_parts = [f"[Review {i}]"]
        if location: header_parts.append(f"Location: {location}")
        if prop:     header_parts.append(f"Property: {prop}")
        if rating:   header_parts.append(f"Overall rating: {rating}/5")
        if title:    header_parts.append(f"Title: \"{title}\"")

        context_parts.append(" | ".join(header_parts) + "\n" + text)

    return "\n\n".join(context_parts)


def generate(question: str, context: str) -> str:
    client = _get_anthropic_client()
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=1024,
        temperature=LLM_TEMPERATURE,
        system=SYSTEM_PROMPT,
        messages=[{
            "role":    "user",
            "content": USER_PROMPT_TEMPLATE.format(
                question=question,
                context=context,
            )
        }],
    )
    return response.content[0].text


def query(question: str,
          top_k: int = RETRIEVAL_TOP_K,
          city_filter: str = None,
          min_rating: int = None) -> dict:
    """
    Pipeline RAG completa: retrieval da Pinecone + generation con Claude.

    Returns:
        {
            "answer":  str,
            "sources": list[dict],
            "mode":    "naive-pinecone",
            "query":   str,
        }
    """
    documents = retrieve(question, top_k=top_k,
                         city_filter=city_filter,
                         min_rating=min_rating)

    if not documents:
        return {
            "answer":  "No relevant reviews found for your question.",
            "sources": [],
            "mode":    "naive-pinecone",
            "query":   question,
        }

    context = build_context(documents)
    answer  = generate(question, context)

    return {
        "answer":  answer,
        "sources": documents,
        "mode":    "naive-pinecone",
        "query":   question,
    }


if __name__ == "__main__":
    print("=" * 55)
    print("ELH RAG — Naive Pipeline / Pinecone (test)")
    print("Digita 'exit' per uscire")
    print("=" * 55)

    test_questions = [
        "Find rooms where students mention a comfortable bed",
        "Which landlords are described as responsive and helpful?",
        "Are there any complaints about cleanliness?",
        "Properties with good WiFi for studying",
        "Rooms suitable for students with pets",
    ]

    print("\nDomande di test:")
    for i, q in enumerate(test_questions, 1):
        print(f"  [{i}] {q}")
    print()

    while True:
        user_input = input(">>> ").strip()
        if user_input.lower() in ("exit", "quit", "q"):
            break
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(test_questions):
                question = test_questions[idx]
                print(f"Domanda: {question}\n")
            else:
                print("Numero non valido.")
                continue
        else:
            question = user_input
        if not question:
            continue

        print("Searching on Pinecone...\n")
        result = query(question)

        print("─" * 55)
        print("RISPOSTA:")
        print(result["answer"])
        print(f"\nFONTI ({len(result['sources'])} review da Pinecone):")
        for i, src in enumerate(result["sources"], 1):
            meta  = src["metadata"]
            score = src.get("score", 0)
            print(f"  [{i}] {meta.get('zone','')}, {meta.get('city','')} "
                  f"— {meta.get('flatname','')} (score: {score:.3f})")
        print("─" * 55 + "\n")