# embeddings.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Build and return the embedding model used throughout the
#   pipeline — both at ingestion time (to embed chunks) and
#   at query time (to embed the user's question).
#
# The SAME model instance must be used in both places.
# Using different models would produce incompatible vector spaces
# and retrieval would return completely wrong results.
#
# This module is intentionally small — one job, one function.
# Other modules (ingest.py, retriever.py) import from here so
# the model is never instantiated in more than one place.
# ─────────────────────────────────────────────────────────────

import logging
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)


# ── Model choice ──────────────────────────────────────────────
# "all-MiniLM-L6-v2" is the industry-standard free embedding model
# for RAG projects. Here's why it's the right choice:
#
#   • 384-dimensional vectors — compact, fast to store and search
#   • 512 token input limit — fits most paragraph-length chunks
#   • ~90MB on disk — small enough to load on free-tier servers
#   • Trained on 1B+ sentence pairs — strong semantic understanding
#   • Runs entirely on CPU — no GPU required
#
# The "sentence-transformers/" prefix tells HuggingFace to look
# for this model in the sentence-transformers organisation on the
# HuggingFace model hub.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


# ─────────────────────────────────────────────────────────────
# get_embedding_model()
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    Load and return the HuggingFace embedding model.

    Uses @lru_cache so the model is downloaded and loaded only
    once per process, no matter how many times this function is
    called. Loading the model takes ~2-3 seconds and ~90MB of RAM
    — we don't want to pay that cost on every request.

    Returns:
        HuggingFaceEmbeddings: A LangChain-compatible embedding
        model ready to embed text strings into vectors.
    """

    logger.info(f"Loading embedding model: '{EMBEDDING_MODEL_NAME}'")
    logger.info("This may take a moment on first run (downloading ~90MB)...")

    # ── HuggingFaceEmbeddings constructor ─────────────────────
    # LangChain's HuggingFaceEmbeddings is a wrapper around the
    # sentence-transformers library. It provides a standard
    # .embed_documents() and .embed_query() interface that
    # FAISS, Pinecone, and LangChain chains all expect.
    embedding_model = HuggingFaceEmbeddings(
        # model_name: which model to download from HuggingFace Hub.
        # On first run, this downloads the model weights to a local
        # cache (~/.cache/huggingface/). Subsequent runs load from
        # the cache — no internet required after the first run.
        model_name=EMBEDDING_MODEL_NAME,

        # model_kwargs: passed directly to the underlying
        # sentence-transformers model constructor.
        # "device": "cpu" explicitly runs on CPU.
        # Change to "cuda" if you have an NVIDIA GPU — embeddings
        # would be significantly faster for large document sets.
        model_kwargs={"device": "cpu"},

        # encode_kwargs: controls how text is converted to vectors.
        # "normalize_embeddings": True scales every vector to unit
        # length (magnitude = 1). This makes cosine similarity
        # equivalent to dot product, which is faster to compute
        # and is required for FAISS's inner product index type.
        encode_kwargs={"normalize_embeddings": True},
    )

    logger.info("Embedding model loaded successfully.")
    return embedding_model


# ─────────────────────────────────────────────────────────────
# Manual test — run directly to verify the model works
# python -m app.embeddings
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    model = get_embedding_model()

    # ── Test 1: Embed a single query ──────────────────────────
    # embed_query() is used at request time — converts the user's
    # question into a vector for similarity search.
    test_query = "How do I return a product?"
    query_vector = model.embed_query(test_query)

    logger.info(f"\nQuery : '{test_query}'")
    logger.info(f"Vector dimensions : {len(query_vector)}")
    logger.info(f"First 5 values    : {[round(v, 4) for v in query_vector[:5]]}")

    # ── Test 2: Semantic similarity check ────────────────────
    # This demonstrates the core value of embeddings:
    # semantically similar sentences produce close vectors.
    import numpy as np

    sentences = [
        "How do I return a product?",        # the query
        "What is your refund policy?",        # similar meaning
        "How do I reset my password?",        # unrelated
        "Can I get my money back?",           # paraphrase
    ]

    # embed_documents() is used at ingestion time — converts
    # a list of text chunks into a list of vectors for storage.
    vectors = model.embed_documents(sentences)

    # Compute cosine similarity between query (index 0) and others.
    # Since vectors are normalized, dot product = cosine similarity.
    query_vec = np.array(vectors[0])

    logger.info("\nSemantic similarity to: 'How do I return a product?'")
    logger.info("─" * 50)

    for i, sentence in enumerate(sentences[1:], start=1):
        other_vec = np.array(vectors[i])

        # np.dot(a, b) computes the dot product of two vectors.
        # For unit-length vectors, this equals cosine similarity.
        # Result: 1.0 = identical, 0.0 = unrelated, -1.0 = opposite
        similarity = float(np.dot(query_vec, other_vec))

        logger.info(f"  {similarity:.4f}  →  '{sentence}'")

    logger.info("─" * 50)
    logger.info("Higher score = more similar meaning.")
    logger.info("\nEmbedding model is working correctly.")
