# embeddings.py
# Uses Google's text-embedding-004 via direct HTTP calls (v1 API).
# Bypasses all SDKs to avoid v1beta issues.

import logging
from functools import lru_cache
from typing import List

import httpx
from langchain_core.embeddings import Embeddings

from app.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "text-embedding-004"
EMBED_URL = f"https://generativelanguage.googleapis.com/v1/models/{EMBEDDING_MODEL_NAME}:batchEmbedContents"


class GoogleGenAIEmbeddings(Embeddings):
    """Direct HTTP calls to Google v1 API for embeddings."""

    def _embed_batch(self, texts: List[str], task_type: str) -> List[List[float]]:
        requests_payload = [
            {
                "model": f"models/{EMBEDDING_MODEL_NAME}",
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
            }
            for t in texts
        ]
        response = httpx.post(
            EMBED_URL,
            params={"key": GOOGLE_API_KEY},
            json={"requests": requests_payload},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"]["values"] for item in data["embeddings"]]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            result.extend(self._embed_batch(batch, "RETRIEVAL_DOCUMENT"))
        return result

    def embed_query(self, text: str) -> List[float]:
        return self._embed_batch([text], "RETRIEVAL_QUERY")[0]


@lru_cache(maxsize=1)
def get_embedding_model() -> GoogleGenAIEmbeddings:
    logger.info(f"Initialising Google embedding model: '{EMBEDDING_MODEL_NAME}' (direct v1 API)")
    model = GoogleGenAIEmbeddings()
    logger.info("Google embedding model ready.")
    return model
