# embeddings.py
# Uses Google's text-embedding-004 via langchain-google-genai 1.x (v1 API).
# No local model weights — works on free-tier servers.

import logging
from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

# models/ prefix required for langchain-google-genai 1.x
# text-embedding-004 produces 768-dim vectors, matches Pinecone index
EMBEDDING_MODEL_NAME = "models/text-embedding-004"


@lru_cache(maxsize=1)
def get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    logger.info(f"Initialising Google embedding model: '{EMBEDDING_MODEL_NAME}'")

    embedding_model = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        google_api_key=GOOGLE_API_KEY,
        task_type="retrieval_document",
    )

    logger.info("Google embedding model ready.")
    return embedding_model
