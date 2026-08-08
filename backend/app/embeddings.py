# embeddings.py
# Uses Google's text-embedding-004 via google-genai SDK.
# AQ. format keys only work with google-genai SDK, not REST API.

import logging
from functools import lru_cache
from typing import List

from langchain_core.embeddings import Embeddings
from google import genai
from google.genai import types

from app.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "gemini-embedding-001"


class GoogleGenAIEmbeddings(Embeddings):
    """LangChain-compatible wrapper using google-genai SDK."""

    def __init__(self):
        self.client = genai.Client(api_key=GOOGLE_API_KEY)

    def _embed_batch(self, texts: List[str], task_type: str) -> List[List[float]]:
        contents = [types.Content(parts=[types.Part(text=t)]) for t in texts]
        response = self.client.models.embed_content(
            model=EMBEDDING_MODEL_NAME,
            contents=contents,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=768,
            ),
        )
        return [e.values for e in response.embeddings]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        import time
        result = []
        for i in range(0, len(texts), 80):  # 80 per batch to stay under 100/min
            if i > 0:
                time.sleep(65)  # wait 65 seconds between batches
            batch = texts[i:i+80]
            logger.info(f"Embedding batch {i//80 + 1} of {(len(texts)-1)//80 + 1} ({len(batch)} chunks)...")
            result.extend(self._embed_batch(batch, "RETRIEVAL_DOCUMENT"))
        return result

    def embed_query(self, text: str) -> List[float]:
        return self._embed_batch([text], "RETRIEVAL_QUERY")[0]


@lru_cache(maxsize=1)
def get_embedding_model() -> GoogleGenAIEmbeddings:
    logger.info(f"Initialising Google embedding model: '{EMBEDDING_MODEL_NAME}'")
    model = GoogleGenAIEmbeddings()
    logger.info("Google embedding model ready.")
    return model
