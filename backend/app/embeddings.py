# embeddings.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Build and return the embedding model used throughout the
#   pipeline — both at ingestion time (to embed chunks) and
#   at query time (to embed the user's question).
#
# Uses Google's text-embedding-004 model via the Gemini API.
# This is an API call — no model weights are loaded locally,
# so it works fine on free-tier servers with limited RAM.
#
# Dimensions: 768 (text-embedding-004 default)
# ─────────────────────────────────────────────────────────────

import logging
from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "models/embedding-001"


@lru_cache(maxsize=1)
def get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """
    Return the Google Generative AI embedding model.

    Uses @lru_cache so the client is created only once per process.
    No model weights are downloaded — all embedding is done via
    the Google API, making this suitable for low-memory deployments.

    Returns:
        GoogleGenerativeAIEmbeddings: LangChain-compatible embedding
        model that produces 768-dimensional vectors.
    """
    logger.info(f"Initialising Google embedding model: '{EMBEDDING_MODEL_NAME}'")

    embedding_model = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        google_api_key=GOOGLE_API_KEY,
    )

    logger.info("Google embedding model ready.")
    return embedding_model
