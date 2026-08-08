# embeddings.py
# Uses Google's text-embedding-004 via the google-genai SDK directly.
# Wraps it in a LangChain-compatible interface.
# No local model weights — works on free-tier servers.

import logging
from functools import lru_cache
from typing import List

from langchain_core.embeddings import Embeddings
from google import genai
from google.genai import types

from app.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "text-embedding-004"


class GoogleGenAIEmbeddings(Embeddings):
    """LangChain-compatible wrapper around google-genai SDK embeddings."""

    def __init__(self):
        self.client = genai.Client(api_key=GOOGLE_API_KEY)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = []
        # Process in batches of 100 (API limit)
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self.client.models.embed_content(
                model=EMBEDDING_MODEL_NAME,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
            result.extend([e.values for e in response.embeddings])
        return result

    def embed_query(self, text: str) -> List[float]:
        response = self.client.models.embed_content(
            model=EMBEDDING_MODEL_NAME,
            contents=[text],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
            ),
        )
        return response.embeddings[0].values


@lru_cache(maxsize=1)
def get_embedding_model() -> GoogleGenAIEmbeddings:
    logger.info(f"Initialising Google embedding model: '{EMBEDDING_MODEL_NAME}'")
    model = GoogleGenAIEmbeddings()
    logger.info("Google embedding model ready.")
    return model
