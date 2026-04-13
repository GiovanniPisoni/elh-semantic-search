import os
import json
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH     = os.getenv("CHROMA_PATH", "./data/chroma_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL",
                             "paraphrase-multilingual-mpnet-base-v2")
LLM_MODEL       = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
 
COLLECTION_NAME = "elh_reviews"

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
- Respond in the same language as the user's question \
(English or Portuguese).
"""
 
USER_PROMPT_TEMPLATE = """Based on the following student reviews, please answer this question:
 
Question: {question}
 
---
STUDENT REVIEWS:
{context}
---
 
Please provide a clear, helpful answer citing the relevant reviews."""

_embedding_model = None
_chroma_collection = None
_anthropic_client = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    
    return _embedding_model

def _get_collection():
    global _chroma_collection
    if _chroma_collection is None:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _chroma_collection = client.get_collection(COLLECTION_NAME)
    
    return _chroma_collection

def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

    return _anthropic_client

def retrive(question: str, top_k: int = RETRIEVAL_TOP_K,
            city_filter: str = None,
            min_rating: int  = None) -> list[dict]:
    
    model = _get_embedding_model()
    collection = _get_collection()

    question_embedding = model.encode(
        question,
        normalize_embeddings=True
    ).tolist()

    where = None
    if city_filter and min_rating:
        where = {
            "$and": [
                {"city": {"$eq": city_filter}},
                {"overall_rating": {"$eq": min_rating}},
            ]
        }
    elif city_filter:
        where = {"city": {"$eq": city_filter}}
    elif min_rating:
        where = {"overall_rating": {"$eq": min_rating}}

    query_params = {
        "query_embeddings": [question_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        query_params["where"] = where
    
    results = collection.query(**query_params)

    documents = []

    for i in range(len(results["ids"][0])):
        documents.append({
            "text": results["documents"][0][i],
            "metadata":  results["metadatas"][0][i],
            "distance":  results["distances"][0][i],
            "score":     round(1 - results["distances"][0][i], 3),
        })

    return documents

def build_context(documents: list[dict]) -> str:
    context_parts = []

    for i, doc in enumerate(documents, 1):
        meta = doc["metadata"]
        city = meta.get("city", "")
        zone = meta.get("zone", "")
        flatname = meta.get("flatname", "")
        roomname = meta.get("roomname", "")
        rating = meta.get("overall_rating", "")
        title = meta.get("review_title", "")
        text = meta.get("review_text_original", doc["text"])

        location = ", ".join(filter(None, [zone, city]))
        property_name = " — ".join(filter(None, [flatname, roomname]))

        header_parts = ["f[Review {i}]"]
        if location:
            header_parts.append(f"Location: {location}")
        if property_name:
            header_parts.append(f"Property: {property_name}")
        if rating:
            header_parts.append(f"Overall rating: {rating}/5")
        if title:
            header_parts.append(f"Title: \"{title}\"")

        header = " | ".join(header_parts)
        context_parts.append(f"{header}\n{text}")

    return "\n\n".join(context_parts)

def generate(question: str, context: str) -> str:
    client = _get_anthropic_client()

    user_msg = USER_PROMPT_TEMPLATE.format(
        question=question,
        context=context
    )

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=1024,
        temperature=LLM_TEMPERATURE,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_msg}
        ]
    )

    return response.content[0].text

def query(question: str,
          top_k: int = RETRIEVAL_TOP_K,
          city_filter: str = None,
          min_rating: int = None) -> dict:
    
    documents = retrive(question, top_k=top_k,
                        city_filter=city_filter,
                        min_rating=min_rating)
    
    if not documents:
        return {
            "answer": "No relevant reviews found for you question.",
            "sources": [],
            "mode": "naive",
            "query": question,
        }
    
    context = build_context(documents)
    answer = generate(question, context)

    return {
        "answer": answer,
        "sources": documents,
        "mode": "naive",
        "query": question,
    }


if __name__ == "__main__":
    print("=" * 55)
    print("ELH RAG — Naive Pipeline (interactive test)")
    print("Digit 'exit' to close")
    print("=" * 55)

    test_questions = [
        "Find rooms where students mention a comfortable bed",
        "Which landlords are described as responsive and helpful?",
        "Are there any complaints about cleanliness?",
        "Properties with good WiFi for studying",
        "Rooms suitable for students with pets",
    ]

    print("\nDomande di test predisposte:")
    for i, q in enumerate(test_questions, 1):
        print(f"  [{i}] {q}")
 
    print("\nDigita il numero di una domanda o scrivi la tua:\n")
 
    while True:
        user_input = input(">>> ").strip()
 
        if user_input.lower() in ("exit", "quit", "q"):
            break
 
        # Selezione domanda predefinita
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
 
        print("Searching...\n")
        result = query(question)
 
        print("─" * 55)
        print("RISPOSTA:")
        print(result["answer"])
 
        print(f"\nFONTI ({len(result['sources'])} review recuperate):")
        for i, src in enumerate(result["sources"], 1):
            meta = src["metadata"]
            city  = meta.get("city", "")
            zone  = meta.get("zone", "")
            flat  = meta.get("flatname", "")
            score = src.get("score", 0)
            print(f"  [{i}] {zone}, {city} — {flat} "
                  f"(similarity: {score:.3f})")
 
        print("─" * 55 + "\n")