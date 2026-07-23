# retriever.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Load the FAISS vector store once at server startup, then
#   expose two interfaces for querying it:
#
#   1. get_retriever() → LangChain Retriever object
#      Used by the RAG chain (chain.py) — LangChain handles
#      the embedding and search internally.
#
#   2. retrieve_chunks() → List[Document]
#      Used directly when you need explicit control over
#      retrieval (testing, debugging, custom logic).
#
# The vector store is loaded once and cached for the lifetime
# of the server process. No disk reads happen at request time.
# ─────────────────────────────────────────────────────────────

import logging
from functools import lru_cache
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from app.config import ENVIRONMENT, RETRIEVER_K
from app.vectorstore import load_vectorstore

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# _get_vectorstore()  [private, cached]
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_vectorstore() -> FAISS:
    """
    Load and cache the FAISS vector store from disk.

    Private function — other modules should use get_retriever()
    or retrieve_chunks() instead of calling this directly.

    The @lru_cache decorator ensures the vector store is loaded
    from disk exactly once per process. Every subsequent call
    returns the same in-memory object instantly.

    This matters because loading the vector store reads
    index.faiss and index.pkl from disk, deserializes them,
    and loads the embedding model — a multi-second operation
    you never want happening mid-request.

    Returns:
        FAISS: The loaded, search-ready vector store.
    """
    logger.info("Loading FAISS vector store into memory (first request)...")

    # load_vectorstore() reads both index files from disk and
    # reconstructs the full FAISS object. Defined in vectorstore.py.
    vectorstore = load_vectorstore()

    logger.info(
        f"Vector store ready — {vectorstore.index.ntotal} vectors loaded."
    )
    return vectorstore


# ─────────────────────────────────────────────────────────────
# _get_pinecone_vectorstore()  [private, cached]
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_pinecone_vectorstore():
    """
    Connect to and cache the Pinecone vector store.

    Private function — called by get_retriever() when ENVIRONMENT="production".
    Uses deferred imports so that langchain-pinecone is never imported
    in development (where it may not be installed).

    The @lru_cache ensures Pinecone connects exactly once per process.
    """
    # Deferred imports: only loaded in production.
    from app.pinecone_store import get_pinecone_store
    from app.embeddings import get_embedding_model

    logger.info("Connecting to Pinecone vector store (production backend)...")
    return get_pinecone_store(get_embedding_model())


# ─────────────────────────────────────────────────────────────
# get_retriever()
# ─────────────────────────────────────────────────────────────

def get_retriever() -> VectorStoreRetriever:
    """
    Return a LangChain VectorStoreRetriever for the active backend.

    Routes to the correct vector store based on ENVIRONMENT:
      - "development"  → FAISS (local file, loaded by _get_vectorstore)
      - "production"   → Pinecone (cloud, loaded by _get_pinecone_vectorstore)
      - anything else  → raises ValueError at startup (fail-fast)

    The public signature (() -> VectorStoreRetriever) is unchanged —
    callers (chain.py, main.py) do not need to know which backend is active.
    """
    if ENVIRONMENT == "development":
        vectorstore = _get_vectorstore()
    elif ENVIRONMENT == "production":
        vectorstore = _get_pinecone_vectorstore()
    else:
        raise ValueError(
            f"Invalid ENVIRONMENT value: '{ENVIRONMENT}'. "
            "Must be 'development' or 'production'."
        )

    retriever: VectorStoreRetriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVER_K},
    )

    return retriever


# ─────────────────────────────────────────────────────────────
# retrieve_chunks()
# ─────────────────────────────────────────────────────────────

def retrieve_chunks(query: str, k: int = RETRIEVER_K) -> List[Document]:
    """
    Embed a query and return the top-K most relevant chunks.

    This is the explicit, lower-level retrieval interface.
    Use this when you need direct access to results with scores,
    for testing retrieval quality, or for custom logic that
    doesn't fit into the LangChain chain pattern.

    Args:
        query: The user's natural language question.
        k:     Number of chunks to return. Defaults to RETRIEVER_K
               from config (default: 4). Pass k=3 to match the
               project requirement of top 3 results.

    Returns:
        List[Document]: The top-K most semantically similar chunks,
        ordered from most to least similar. Each Document contains:
            - page_content (str): The chunk text
            - metadata (dict): source filename, page number, etc.
    """

    if not query or not query.strip():
        raise ValueError(
            "Query cannot be empty. "
            "Provide a non-empty question string."
        )

    vectorstore = _get_vectorstore()

    logger.info(f"Retrieving top-{k} chunks for query: '{query[:80]}...'")

    # ── similarity_search() ───────────────────────────────────
    # This is what actually does the work:
    #
    #   1. Calls embedding_model.embed_query(query) internally
    #      to convert the question into a 384-dim vector.
    #      It uses the SAME embedding model that was used at
    #      ingestion time — stored inside the vectorstore object.
    #
    #   2. Calls FAISS's search() on the index with that vector,
    #      computing L2 distance against all stored vectors.
    #
    #   3. Returns the k Document objects whose vectors have the
    #      smallest L2 distance (most similar meaning) to the
    #      query vector.
    #
    # The result is ordered: index 0 = most similar, index k-1 =
    # least similar among the returned results.
    docs: List[Document] = vectorstore.similarity_search(
        query=query,   # raw text — embedding happens inside
        k=k,           # number of results to return
    )

    # ── Log what was retrieved ────────────────────────────────
    # Logging retrieval results is important for debugging.
    # If the chatbot gives wrong answers, this is the first place
    # to check — are the right chunks being retrieved?
    logger.info(f"Retrieved {len(docs)} chunk(s):")
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "?")
        # Log just the filename, not the full path
        filename = source.split("\\")[-1].split("/")[-1]
        preview = doc.page_content[:80].replace("\n", " ")
        logger.info(f"  [{i}] {filename} (p.{page}) — \"{preview}...\"")

    return docs


# ─────────────────────────────────────────────────────────────
# retrieve_chunks_with_scores()
# ─────────────────────────────────────────────────────────────

def retrieve_chunks_with_scores(
    query: str, k: int = RETRIEVER_K
) -> List[tuple[Document, float]]:
    """
    Like retrieve_chunks(), but also returns similarity scores.

    Useful for evaluating retrieval quality — you can see exactly
    how similar each retrieved chunk is to the query. Low scores
    on top results indicate the query doesn't match the documents
    well, which points to a knowledge gap in your document set.

    Args:
        query: The user's natural language question.
        k:     Number of results to return.

    Returns:
        List of (Document, score) tuples, ordered by score
        descending. Score is cosine similarity (0.0 to 1.0 for
        normalized vectors). Higher = more similar.
    """

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    vectorstore = _get_vectorstore()

    # similarity_search_with_score() returns (Document, float) tuples.
    # The float is the L2 distance — lower is better (closer vectors).
    # For normalized vectors, L2 distance and cosine similarity are
    # directly related: similarity = 1 - (distance / 2)
    results: List[tuple[Document, float]] = (
        vectorstore.similarity_search_with_score(query=query, k=k)
    )

    logger.info(f"Retrieved {len(results)} chunk(s) with scores:")
    for i, (doc, score) in enumerate(results, start=1):
        source = doc.metadata.get("source", "unknown")
        filename = source.split("\\")[-1].split("/")[-1]
        # Convert L2 distance to a 0-1 similarity score
        # so it's easier to interpret (1.0 = identical).
        similarity = 1 / (1 + score)
        logger.info(f"  [{i}] score={similarity:.3f} | {filename}")

    return results


# ─────────────────────────────────────────────────────────────
# Manual test — run directly to verify retrieval works
# python -m app.retriever
#
# Requires: vector store must already exist (run ingest.py first)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # ── Test questions ────────────────────────────────────────
    # These test different scenarios:
    #   - Direct keyword match (should score high)
    #   - Paraphrase / different wording (tests semantic search)
    #   - Completely unrelated (should score low — tests boundaries)
    test_queries = [
        "How do I return a product?",
        "Can I get my money back?",           # paraphrase of above
        "What is the shipping cost?",
        "How do I reset my password?",        # probably not in docs
    ]

    logger.info("═" * 55)
    logger.info("RETRIEVAL TEST")
    logger.info("═" * 55)

    for query in test_queries:
        logger.info(f"\nQuery: '{query}'")
        logger.info("─" * 55)

        # retrieve_chunks_with_scores() so we can see how confident
        # the retrieval is — low scores = weak matches
        results = retrieve_chunks_with_scores(query, k=3)

        for rank, (doc, raw_score) in enumerate(results, start=1):
            source = doc.metadata.get("source", "unknown")
            filename = source.split("\\")[-1].split("/")[-1]
            page = doc.metadata.get("page", "?")
            similarity = 1 / (1 + raw_score)

            # Print the full chunk content so you can visually
            # verify it's relevant to the question
            logger.info(f"  Rank {rank} | sim={similarity:.3f} | {filename} p.{page}")
            logger.info(f"  {doc.page_content[:200].replace(chr(10), ' ')}")
            logger.info("")

    logger.info("═" * 55)
    logger.info("Retrieval test complete.")
