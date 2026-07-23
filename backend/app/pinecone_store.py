# pinecone_store.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Pinecone cloud vector store integration.
#   Only imported when ENVIRONMENT="production".
#   All functions here deal exclusively with Pinecone —
#   the FAISS path in retriever.py and vectorstore.py is
#   completely untouched.
#
# Three public functions:
#   get_pinecone_store(embedding_model) → PineconeVectorStore
#     Connects once per process (lru_cache). Used by the retriever.
#
#   upsert_to_pinecone(chunks, embedding_model=None) → int
#     Adds documents to an existing Pinecone index. Used by
#     upload endpoints (chat.py) after runtime document uploads.
#
#   build_pinecone_store(chunks, embedding_model=None) → PineconeVectorStore
#     Creates/replaces the index contents from scratch. Used by
#     the ingestion pipeline (ingest.py).
# ─────────────────────────────────────────────────────────────

import logging
from typing import List

from app.config import PINECONE_API_KEY, PINECONE_INDEX_NAME

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# get_pinecone_store()  [cached — connects once per process]
# ─────────────────────────────────────────────────────────────

# Module-level singleton — replaces lru_cache since HuggingFaceEmbeddings
# is not hashable in newer versions of langchain-huggingface.
_pinecone_store_instance = None


def get_pinecone_store(embedding_model):
    """
    Connect to the Pinecone index and return a PineconeVectorStore.

    Uses a module-level singleton so Pinecone connects exactly once per
    process regardless of how many times this function is called.

    The embedding_model is accepted as a parameter so tests can inject
    a mock embedding model without triggering real network calls.

    Args:
        embedding_model: A HuggingFaceEmbeddings instance (or mock).

    Returns:
        PineconeVectorStore: Connected to PINECONE_INDEX_NAME.

    Raises:
        Exception: Any Pinecone connection error is propagated to the caller.
    """
    global _pinecone_store_instance
    if _pinecone_store_instance is not None:
        return _pinecone_store_instance

    from langchain_pinecone import PineconeVectorStore

    logger.info(
        f"Connecting to Pinecone index '{PINECONE_INDEX_NAME}' "
        "(first call — result will be cached)..."
    )

    _pinecone_store_instance = PineconeVectorStore(
        index_name=PINECONE_INDEX_NAME,
        embedding=embedding_model,
        pinecone_api_key=PINECONE_API_KEY,
    )

    logger.info(f"Pinecone store ready (index='{PINECONE_INDEX_NAME}').")
    return _pinecone_store_instance


# ─────────────────────────────────────────────────────────────
# upsert_to_pinecone()
# ─────────────────────────────────────────────────────────────

def upsert_to_pinecone(chunks: List, embedding_model=None) -> int:
    """
    Embed and upsert a list of document chunks into the Pinecone index.

    Used by upload endpoints (chat.py) after a user uploads a new PDF
    at runtime — the new chunks are merged into the existing index.

    Args:
        chunks:          List of LangChain Document objects to upsert.
        embedding_model: Optional embedding model. If None, falls back
                         to get_embedding_model() from app.embeddings.

    Returns:
        int: The number of chunks successfully upserted.

    Raises:
        Exception: Any Pinecone or embedding error is logged at ERROR
                   level with full traceback, then re-raised so the
                   caller can handle it (e.g. return 422 to the client).
    """
    if embedding_model is None:
        from app.embeddings import get_embedding_model
        embedding_model = get_embedding_model()

    try:
        store = get_pinecone_store(embedding_model)
        store.add_documents(chunks)
        logger.info(f"Upserted {len(chunks)} chunk(s) to Pinecone index '{PINECONE_INDEX_NAME}'.")
        return len(chunks)
    except Exception:
        logger.error(
            f"Failed to upsert {len(chunks)} chunk(s) to Pinecone index '{PINECONE_INDEX_NAME}'.",
            exc_info=True,
        )
        raise


# ─────────────────────────────────────────────────────────────
# build_pinecone_store()
# ─────────────────────────────────────────────────────────────

def build_pinecone_store(chunks: List, embedding_model=None):
    """
    Build (or rebuild) the Pinecone index from a list of document chunks.

    Mirrors the interface of build_vectorstore() in vectorstore.py so
    ingest.py can call either function with the same arguments depending
    on ENVIRONMENT.

    Unlike upsert_to_pinecone(), this function uses from_documents()
    which is designed for initial population of an index. In practice
    both methods add vectors to Pinecone; from_documents() is the
    idiomatic LangChain pattern for bulk ingestion.

    Args:
        chunks:          List of LangChain Document objects.
        embedding_model: Optional embedding model. If None, falls back
                         to get_embedding_model() from app.embeddings.

    Returns:
        PineconeVectorStore: The connected store after ingestion.
    """
    from langchain_pinecone import PineconeVectorStore

    if embedding_model is None:
        from app.embeddings import get_embedding_model
        embedding_model = get_embedding_model()

    logger.info(
        f"Building Pinecone store from {len(chunks)} chunk(s) "
        f"into index '{PINECONE_INDEX_NAME}'..."
    )

    store = PineconeVectorStore.from_documents(
        documents=chunks,
        embedding=embedding_model,
        index_name=PINECONE_INDEX_NAME,
        pinecone_api_key=PINECONE_API_KEY,
    )

    logger.info(
        f"Pinecone store built — {len(chunks)} chunk(s) "
        f"ingested into '{PINECONE_INDEX_NAME}'."
    )
    return store
