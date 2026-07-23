# config.py
# ─────────────────────────────────────────────────────────────
# Central configuration module.
# Every other module imports settings from here.
# No other module should read .env or os.environ directly.
# ─────────────────────────────────────────────────────────────

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Locate the .env file ──────────────────────────────────────
# __file__ is the absolute path to this config.py file.
# .parent      → app/
# .parent.parent → backend/
# We look for .env in the backend/ directory.
BASE_DIR = Path(__file__).resolve().parent.parent

# load_dotenv() reads the .env file and injects its key=value
# pairs into os.environ so os.getenv() can find them.
load_dotenv(BASE_DIR / ".env")


# ── Paths ─────────────────────────────────────────────────────

# Folder where raw PDF/TXT source documents are stored.
DOCUMENTS_DIR = BASE_DIR / "documents"

# Folder where the FAISS index files will be saved (local dev only).
VECTORSTORE_DIR = BASE_DIR / "vectorstore"

# SQLite database file for chat history persistence.
# A single file — zero config, works on all platforms.
DATABASE_PATH = BASE_DIR / "history.db"


# ── API Keys ──────────────────────────────────────────────────

# Google Gemini API key — used for both embeddings (production)
# and LLM generation.
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# Gemini model name.
# gemini-1.5-flash is the current stable default.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Pinecone credentials — only needed when deploying to production.
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "support-chatbot")


# ── JWT Settings ──────────────────────────────────────────────

# Secret key used to sign JWT tokens.
# MUST be a long random string in production.
# Generate one with:  python -c "import secrets; print(secrets.token_hex(32))"
# An empty default is intentionally rejected at startup (see main.py).
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")

# Algorithm used to sign tokens.
# HS256 = HMAC with SHA-256 — symmetric, fast, sufficient for this use case.
# Asymmetric RS256 is only needed when multiple services need to verify tokens.
JWT_ALGORITHM: str = "HS256"

# Access token lifetime in minutes.
# Short window (15 min) limits exposure if a token is stolen.
# The frontend uses the refresh token to get a new one silently.
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))

# Refresh token lifetime in days.
# 7 days means users stay logged in for a week without re-entering credentials.
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


# ── Environment flag ──────────────────────────────────────────

# Controls which vector store backend is used:
#   "development" → FAISS (local file)
#   "production"  → Pinecone (cloud)
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


# ── RAG tuning parameters ─────────────────────────────────────

# Maximum number of characters per text chunk.
# Smaller = more precise retrieval. Larger = more context per chunk.
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))

# Number of characters shared between consecutive chunks.
# Overlap prevents important sentences at chunk boundaries
# from being split and losing their meaning.
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))

# Number of chunks to retrieve for each user question (top-K).
# Retrieves the K most semantically similar chunks.
# Default is 3 — enough context for most support questions
# without flooding the LLM prompt with noise.
RETRIEVER_K: int = int(os.getenv("RETRIEVER_K", "5"))

# Maximum number of prior user+bot message pairs to include in the LLM prompt.
# Each pair = 2 messages (one user, one bot).
# Default of 10 pairs = up to 20 messages in the history block.
# Raise for more context depth; lower to reduce prompt size / token cost.
# MUST be a positive integer — invalid values cause a ValueError at startup.
_raw_window: str = os.getenv("CHAT_HISTORY_WINDOW", "10")
try:
    CHAT_HISTORY_WINDOW: int = int(_raw_window)
    if CHAT_HISTORY_WINDOW <= 0:
        raise ValueError()
except ValueError:
    raise ValueError(
        f"CHAT_HISTORY_WINDOW must be a positive integer. Got: '{_raw_window}'"
    )
