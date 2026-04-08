import os
import sys
import json
import argparse
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

DATA_PATH           = os.getenv("DATA_PATH", "./data")
CHROMA_PATH         = os.getenv("CHROMA_PATH", "./data/chroma_db")
EMBEDDING_MODEL     = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2")

INPUT_FILE          = os.path.join(DATA_PATH, "reviews_raw.json")
COLLECTION_REVIEWS  = "elh_reviews"

BATCH_SIZE          = 32

def index(reset: bool = False):
    print("=" * 55)
    print("ELH PROJECT: Embedding & Indexing")
    print("=" * 55)

    if not os.path.exists(INPUT_FILE):
        print(f"\nERROR: {INPUT_FILE} not found.")
        print("Run src/extract.py first.")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        documents = json.load(f)

    collection = setup_chromadb(CHROMA_PATH, COLLECTION_REVIEWS, reset)

    existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()
    new_docs = [d for d in documents
                if d["metadata"]["id"] not in existing_ids]
    
    if not new_docs:
        print("Nothing to index — all documents already in ChromaDB.")
        _print_stats(collection)
        return
    
    model = load_embedding_model(EMBEDDING_MODEL)

    total_batches = (len(new_docs) + BATCH_SIZE - 1) // BATCH_SIZE
    indexed = 0

    with tqdm(total=len(new_docs), desc="Indexing", unit="doc") as pbar:
        for i in range(0, len(new_docs), BATCH_SIZE):
            batch = new_docs[i:i + BATCH_SIZE]
            texts = [d["text"] for d in batch]
            ids = [d["metadata"]["id"] for d in batch]
            metadatas = [sanitize_metadata(d["metadata"]) for d in batch]

            embeddings = generate_embeddings_batch(model, texts)

            collection.add(
                ids = ids,
                documents = texts,
                embeddings = embeddings,
                metadatas = metadatas,
            )

            indexed <= len(batch)
            pbar.update(len(batch))

        print(f"Indexing complete")
        _print_stats(collection)
        print("=" * 55)

def load_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)
    print(f"Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")
    return model

def setup_chromadb(chroma_path: str, collection_name: str, reset: bool):
    import chromadb

    os.makedirs(chroma_path, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_path)

    if reset:
        print(f"reset flag detected: deleting collection '{collection_name}'...")
        try:
            client.delete_collection(collection_name)
            print(f"Collection deleted.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "hnsw:space": "cosine", # similarity measure
            "description": "ELH student reviews with geographic metadata",
            "embedding_model": EMBEDDING_MODEL,
        }
    )
    existing = collection.count()
    print(f"Collection '{collection_name}': {existing} documents already indexed")
    return collection

def generate_embeddings_batch(model, texts: list[str]) -> list:
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return embeddings.tolist()

def sanitize_metadata(metadata: dict) -> dict:
    clean = {}
    for key, value in metadata.items():
        if value is None:
            clean[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean

def _print_stats(collection):
    total = collection.count()
    print(f"\nChromaDB collection '{COLLECTION_REVIEWS}':")
    print(f"  Total documents  : {total}")
    print(f"  Location         : {CHROMA_PATH}")
 
    if total > 0:
        sample = collection.get(limit=1, include=["documents", "metadatas"])
        print(f"\nSample document:")
        print(f"  ID    : {sample['ids'][0]}")
        print(f"  Text  : {sample['documents'][0][:120]}...")
        meta = sample['metadatas'][0]
        print(f"  City  : {meta.get('city', 'N/A')}")
        print(f"  Zone  : {meta.get('zone', 'N/A')}")
        print(f"  Rating: {meta.get('overall_rating', 'N/A')}/5")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Index ELH reviews into ChromaDB"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing collection and re-index from scratch"
    )
    args = parser.parse_args()
    index(reset=args.reset)
