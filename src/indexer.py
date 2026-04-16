import os
import sys
import argparse
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL",
                                "paraphrase-multilingual-mpnet-base-v2")
PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX     = os.getenv("PINECONE_INDEX_NAME", "elh-reviews")

BATCH_SIZE = 32
UPSERT_BATCH = 100

_embedding_model = None
_pinecone_index  = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        print(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"  Embedding dim: {_embedding_model.get_sentence_embedding_dimension()}")
    return _embedding_model


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX)
    return _pinecone_index


def sanitize_metadata(metadata: dict) -> dict:
    clean = {}
    for key, value in metadata.items():
        if value is None:
            clean[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, list):
            clean[key] = [str(v) for v in value]
        else:
            clean[key] = str(value)
    return clean


def index(reset: bool = False):
    print("=" * 55)
    print("ELH — Indexer (Pinecone / online architecture)")
    print("=" * 55)

    from extract import fetch_documents

    # Caricamento documenti da Supabase (niente file locale)
    print("\nFetching documents from Supabase...")
    documents = fetch_documents(verbose=True)
    print(f"  Total documents: {len(documents)}")

    if not documents:
        print("ERROR: No documents found.")
        sys.exit(1)

    # Connessione Pinecone
    print(f"\nConnecting to Pinecone index '{PINECONE_INDEX}'...")
    index = _get_pinecone_index()
    stats = index.describe_index_stats()
    existing_count = stats.total_vector_count
    print(f"  Vectors already in index: {existing_count}")

    if reset and existing_count > 0:
        print(f"  --reset: deleting all {existing_count} vectors...")
        index.delete(delete_all=True)
        print("  Deleted.")
        existing_ids = set()
    elif existing_count > 0:
        # Recupera IDs esistenti per evitare duplicati
        # Pinecone non ha un "list all IDs" diretto su serverless,
        # quindi usiamo fetch con gli IDs dei documenti attuali
        existing_ids = set(
            doc["metadata"]["id"] for doc in documents
            if _vector_exists(index, doc["metadata"]["id"])
        )
        print(f"  Already indexed (checked): {len(existing_ids)}")
    else:
        existing_ids = set()

    new_docs = [d for d in documents if d["metadata"]["id"] not in existing_ids]
    print(f"  New documents to index: {len(new_docs)}")

    if not new_docs:
        print("\n✓  Nothing to index — all documents already in Pinecone.")
        _print_stats(index)
        return

    model = _get_embedding_model()

    print(f"\nIndexing {len(new_docs)} documents...")
    upsert_buffer = []
    indexed = 0

    with tqdm(total=len(new_docs), desc="Indexing", unit="doc") as pbar:
        for i in range(0, len(new_docs), BATCH_SIZE):
            batch = new_docs[i:i + BATCH_SIZE]
            texts = [d["text"] for d in batch]

            embeddings = model.encode(
                texts,
                batch_size=BATCH_SIZE,
                show_progress_bar=False,
                normalize_embeddings=True,
            ).tolist()

            for doc, emb in zip(batch, embeddings):
                upsert_buffer.append({
                    "id":       doc["metadata"]["id"],
                    "values":   emb,
                    "metadata": sanitize_metadata(doc["metadata"])
                })

            if len(upsert_buffer) >= UPSERT_BATCH:
                index.upsert(vectors=upsert_buffer)
                indexed += len(upsert_buffer)
                upsert_buffer = []

            pbar.update(len(batch))

    if upsert_buffer:
        index.upsert(vectors=upsert_buffer)
        indexed += len(upsert_buffer)

    print(f"\n✓  Indexed {indexed} documents on Pinecone.")
    _print_stats(index)
    print("=" * 55)


def _vector_exists(index, vector_id: str) -> bool:
    try:
        result = index.fetch(ids=[vector_id])
        return vector_id in result.vectors
    except Exception:
        return False


def _print_stats(index):
    stats = index.describe_index_stats()
    print(f"\nPinecone index '{PINECONE_INDEX}':")
    print(f"  Total vectors : {stats.total_vector_count}")
    print(f"  Dimension     : {stats.dimension}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Index ELH reviews into Pinecone"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all vectors and re-index from scratch"
    )
    args = parser.parse_args()
    index(reset=args.reset)