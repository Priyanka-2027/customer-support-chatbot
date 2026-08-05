# main.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Application entry point. Creates the FastAPI app instance,
#   configures cross-cutting concerns (CORS, logging), registers
#   routes, and defines lifecycle events.
#
# This file should stay thin. It wires things together —
# it does not contain business logic.
#
# Start the server:
#   uvicorn app.main:app --reload --port 8000
# ─────────────────────────────────────────────────────────────

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import router as auth_router
from app.chat import router as chat_router
from app.config import ENVIRONMENT, JWT_SECRET_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME
from app.database import init_db

# ── Logging configuration ─────────────────────────────────────
# Configure logging once at the application entry point.
# All modules use logging.getLogger(__name__) which inherits
# this root configuration. Format includes timestamp, level,
# and the specific module that logged the message.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Lifespan — startup and shutdown events
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.

    @asynccontextmanager makes this an async context manager.
    Code before `yield` runs on startup.
    Code after `yield` runs on shutdown.

    FastAPI replaced the older @app.on_event("startup") pattern
    with lifespan in v0.93.0. The lifespan approach is cleaner —
    startup and shutdown logic live together in one function.
    """

    # ── STARTUP ───────────────────────────────────────────────
    logger.info("═" * 55)
    logger.info("Customer Support Chatbot API — Starting up")
    logger.info(f"Environment : {ENVIRONMENT}")
    logger.info("═" * 55)

    # ── Validate JWT secret key ───────────────────────────────
    # Fail fast if the secret is not configured rather than
    # running with an empty key that any attacker can trivially
    # reproduce. The server refuses to start without it.
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set in .env\n"
            "Generate one with:\n"
            "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Then add it to backend/.env:\n"
            "  JWT_SECRET_KEY=<generated_value>"
        )

    # ── Initialise the database ───────────────────────────────
    # Creates tables and indexes if they don't exist yet.
    # Safe to call on every startup — uses IF NOT EXISTS.
    logger.info("Initialising database...")
    await init_db()

    # ── Validate Pinecone credentials (production only) ───────
    # Fail fast if Pinecone env vars are missing rather than
    # letting the server start and fail on the first request.
    if ENVIRONMENT == "production":
        if not PINECONE_API_KEY:
            raise RuntimeError(
                "PINECONE_API_KEY is not set in .env\n"
                "This is required when ENVIRONMENT=production.\n"
                "Add it to backend/.env:\n  PINECONE_API_KEY=<your-key>"
            )
        if not PINECONE_INDEX_NAME:
            raise RuntimeError(
                "PINECONE_INDEX_NAME is not set in .env\n"
                "This is required when ENVIRONMENT=production.\n"
                "Add it to backend/.env:\n  PINECONE_INDEX_NAME=<your-index>"
            )

    # Skip pre-warming on startup — load lazily on first request.
    # This keeps startup fast so the server binds to the port quickly.
    # The embedding model and vector store will be loaded on first /chat call.
    logger.info("Startup complete — model/vector store will load on first request.")

    logger.info("API ready. Listening for requests.")

    # ── yield — application runs here ─────────────────────────
    yield

    # ── SHUTDOWN ──────────────────────────────────────────────
    # Python's garbage collector and lru_cache cleanup happen
    # automatically. We just log the shutdown for audit purposes.
    logger.info("Customer Support Chatbot API — Shutting down.")


# ─────────────────────────────────────────────────────────────
# FastAPI application instance
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    # title and description appear in the auto-generated /docs UI.
    title="Customer Support Chatbot API",
    description=(
        "A Retrieval-Augmented Generation (RAG) API that answers "
        "customer support questions using your documentation as the "
        "knowledge base. Built with FastAPI, LangChain, FAISS, and Gemini."
    ),
    version="1.0.0",

    # docs_url: where Swagger UI is served.
    # Default is /docs — keep this for development.
    # Set to None in production if you want to hide it.
    docs_url="/docs",

    # redoc_url: where ReDoc (alternative API docs) is served.
    redoc_url="/redoc",

    # lifespan: the context manager defined above.
    # Replaces the deprecated on_event("startup") pattern.
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────
# CORS middleware
# ─────────────────────────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing) controls which origins
# (domains) are allowed to make requests to this API.
#
# Why we need this:
#   Browsers block requests from one origin to another by default.
#   React on http://localhost:5173 trying to call FastAPI on
#   http://localhost:8000 is a cross-origin request.
#   Without CORS middleware, the browser silently blocks it.
#
# CORSMiddleware adds the appropriate headers to responses so
# the browser allows the request.

# ── Define allowed origins ────────────────────────────────────
# Origins that are permitted to call this API.
# In production, replace localhost entries with your real domains.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

import os
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

production_frontend_url = os.getenv("FRONTEND_URL", "")
if production_frontend_url:
    ALLOWED_ORIGINS.append(production_frontend_url)

# Also allow all Vercel preview deployments for this project
ALLOWED_ORIGIN_PATTERNS = [
    re.compile(r"https://customer-support-chatbot.*\.vercel\.app$"),
]

def is_origin_allowed(origin: str) -> bool:
    if origin in ALLOWED_ORIGINS:
        return True
    return any(p.match(origin) for p in ALLOWED_ORIGIN_PATTERNS)

_CORS_ALLOW_HEADERS = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
_CORS_ALLOW_METHODS = "GET, POST, PUT, DELETE, OPTIONS, PATCH"

class DynamicCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        origin = request.headers.get("origin", "")
        if request.method == "OPTIONS" and is_origin_allowed(origin):
            from starlette.responses import Response
            response = Response(status_code=204)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = _CORS_ALLOW_METHODS
            response.headers["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
            response.headers["Access-Control-Max-Age"] = "600"
            return response
        response = await call_next(request)
        if is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = _CORS_ALLOW_METHODS
            response.headers["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
        return response

app.add_middleware(DynamicCORSMiddleware)


# ─────────────────────────────────────────────────────────────
# Route registration
# ─────────────────────────────────────────────────────────────

# include_router() mounts all routes defined in chat.py onto
# this application. The prefix "/api/v1" is prepended to every
# route path, so:
#   GET  /health     → GET  /api/v1/health
#   POST /chat       → POST /api/v1/chat
#   POST /upload     → POST /api/v1/upload
#
# Versioning the API (/v1) is best practice — when you need
# to make breaking changes, you add /v2 routes without removing
# /v1, so existing clients keep working.
app.include_router(auth_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


# ─────────────────────────────────────────────────────────────
# Root endpoint — API info
# ─────────────────────────────────────────────────────────────

@app.get("/", tags=["System"], summary="API root")
async def root() -> dict:
    """
    Root endpoint. Returns basic API information.

    Useful for verifying the server is reachable and finding
    the documentation URLs without opening /docs manually.
    """
    return {
        "name": "Customer Support Chatbot API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
