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
            config=types.EmbedContentConfig(task_type=task_type),
        )
        return [e.values for e in response.embeddings]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = []
        for i in range(0, len(texts), 100):
            result.extend(self._embed_batch(texts[i:i+100], "RETRIEVAL_DOCUMENT"))
        return result

    def embed_query(self, text: str) -> List[float]:
        return self._embed_batch([text], "RETRIEVAL_QUERY")[0]


@lru_cache(maxsize=1)
def get_embedding_model() -> GoogleGenAIEmbeddings:
    logger.info(f"Initialising Google embedding model: '{EMBEDDING_MODEL_NAME}'")
    model = GoogleGenAIEmbeddings()
    logger.info("Google embedding model ready.")
    return model
