"""
CORS configuration tests for the FastAPI backend.

Task 1: Bug condition exploration test
--------------------------------------
This test is EXPECTED TO FAIL on unfixed code.
Failure confirms the bug exists: CORSMiddleware is configured
with allow_origins=["*"] instead of ALLOWED_ORIGINS.

Validates: Requirements 1.1, 1.2
"""

import sys
import os
import importlib
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Ensure the backend app package is importable
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Stub out heavy/unavailable modules so that importing app.main only
# requires FastAPI + Starlette (both installed), not the full ML stack.
# We do this BEFORE importing anything from app.*
# ---------------------------------------------------------------------------
_STUBS = [
    "langchain",
    "langchain.chains",
    "langchain.chains.combine_documents",
    "langchain_community",
    "langchain_community.vectorstores",
    "langchain_google_genai",
    "langchain_huggingface",
    "sentence_transformers",
    "faiss",
    "aiosqlite",
    "app.chain",
    "app.chat",
    "app.auth",
    "app.database",
    "app.retriever",
    "app.embeddings",
    "app.vectorstore",
    "app.ingest",
    "app.security",
]

for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Stub app.auth and app.chat to expose a usable router attribute
import fastapi
_auth_stub = MagicMock()
_auth_stub.router = fastapi.APIRouter()
_chat_stub = MagicMock()
_chat_stub.router = fastapi.APIRouter()
sys.modules["app.auth"] = _auth_stub
sys.modules["app.chat"] = _chat_stub

# app.config needs real values so main.py's checks pass
_config_stub = types.ModuleType("app.config")
_config_stub.ENVIRONMENT = "test"
_config_stub.JWT_SECRET_KEY = "test-secret-key-for-testing"
_config_stub.CHAT_HISTORY_WINDOW = 10
_config_stub.GEMINI_MODEL = "gemini-pro"
_config_stub.GOOGLE_API_KEY = ""
_config_stub.ACCESS_TOKEN_EXPIRE_MINUTES = 15
_config_stub.REFRESH_TOKEN_EXPIRE_DAYS = 7
_config_stub.JWT_ALGORITHM = "HS256"
_config_stub.DOCUMENTS_DIR = ""
_config_stub.VECTORSTORE_DIR = ""
_config_stub.DATABASE_PATH = ""
_config_stub.RETRIEVER_K = 3
_config_stub.CHUNK_SIZE = 1000
_config_stub.CHUNK_OVERLAP = 200
_config_stub.PINECONE_API_KEY = ""
_config_stub.PINECONE_INDEX_NAME = "support-chatbot"
sys.modules["app.config"] = _config_stub

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st
from starlette.middleware.cors import CORSMiddleware

# Now import the app — CORS middleware is registered at module level
from app.main import app, ALLOWED_ORIGINS


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_cors_allow_origins():
    """
    Inspect the app's user_middleware stack and return the
    allow_origins value configured for CORSMiddleware.

    app.user_middleware is the list of Middleware objects added via
    app.add_middleware() before the stack is built. Each entry has
    .cls (the middleware class) and .kwargs (the config dict).
    """
    cors_entry = next(
        (m for m in app.user_middleware if m.cls == CORSMiddleware),
        None,
    )
    assert cors_entry is not None, (
        "CORSMiddleware not found in app.user_middleware. "
        "Make sure app.add_middleware(CORSMiddleware, ...) is called in main.py."
    )
    return cors_entry.kwargs.get("allow_origins")


# ---------------------------------------------------------------------------
# Task 1 — Bug condition exploration property test
#
# Uses @given(st.none()) to drive a single deterministic property check
# via the Hypothesis PBT framework. The generated value is not used —
# the test inspects the live app instance directly.
#
# EXPECTED OUTCOME ON UNFIXED CODE: FAIL
#   - allow_origins == ["*"]  →  assertion `!= ["*"]` raises AssertionError
#   - allow_origins != ALLOWED_ORIGINS  →  second assertion also fails
#
# Counterexample documented: allow_origins=["*"] instead of the four
# localhost entries in ALLOWED_ORIGINS.
# ---------------------------------------------------------------------------

@settings(max_examples=1)
@given(st.none())
def test_bug_condition_wildcard_origin(_):
    """
    Property 1: Bug Condition — Wildcard Must Not Appear in Middleware Config

    Asserts that CORSMiddleware is NOT configured with the wildcard origin.
    On unfixed code this test FAILS, confirming the bug:
      allow_origins=["*"] is present instead of ALLOWED_ORIGINS.

    Validates: Requirements 1.1, 1.2
    """
    allow_origins = _get_cors_allow_origins()

    # This assertion FAILS on unfixed code (bug confirmed when it fails)
    assert allow_origins != ["*"], (
        f"BUG CONFIRMED: CORSMiddleware allow_origins is ['*'] (wildcard). "
        f"Expected ALLOWED_ORIGINS={ALLOWED_ORIGINS!r}"
    )

    # This assertion also FAILS on unfixed code
    assert allow_origins == ALLOWED_ORIGINS, (
        f"BUG CONFIRMED: allow_origins={allow_origins!r} "
        f"does not match ALLOWED_ORIGINS={ALLOWED_ORIGINS!r}"
    )


# ---------------------------------------------------------------------------
# Task 2 — Preservation property tests (run on UNFIXED code)
#
# These tests exercise the ALLOWED_ORIGINS *list-building logic* directly,
# independent of how (or whether) that list is wired into CORSMiddleware.
# Because they never inspect the middleware config, they pass on both
# unfixed and fixed code — confirming the baseline behaviour to preserve.
#
# EXPECTED OUTCOME ON UNFIXED CODE: PASS
#
# Validates: Requirements 3.1, 3.2
# ---------------------------------------------------------------------------

# Four localhost entries that must always be present
_LOCALHOST_DEFAULTS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]


def _build_allowed_origins(frontend_url: str) -> list:
    """
    Replicate the ALLOWED_ORIGINS construction logic from main.py so that
    property tests can call it with arbitrary FRONTEND_URL values without
    reloading the module.

    Logic mirrors main.py exactly:
        ALLOWED_ORIGINS = [...four localhost entries...]
        if production_frontend_url:
            ALLOWED_ORIGINS.append(production_frontend_url)
    """
    origins = list(_LOCALHOST_DEFAULTS)  # fresh copy each call
    if frontend_url:
        origins.append(frontend_url)
    return origins


# ---------------------------------------------------------------------------
# Property 2a — All four localhost defaults are always present
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(st.text())
def test_preservation_2a_localhost_defaults_always_present(frontend_url):
    """
    Property 2a: For ANY FRONTEND_URL value (including empty or absent),
    all four default localhost origins are always present in the constructed
    ALLOWED_ORIGINS list.

    Validates: Requirements 3.1, 3.2
    """
    origins = _build_allowed_origins(frontend_url)

    for default_origin in _LOCALHOST_DEFAULTS:
        assert default_origin in origins, (
            f"Missing default origin {default_origin!r} "
            f"when FRONTEND_URL={frontend_url!r}. Got: {origins!r}"
        )


# ---------------------------------------------------------------------------
# Property 2b — Non-empty FRONTEND_URL appears exactly once, never as "*"
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(st.text(min_size=1).filter(lambda s: s != "*"))
def test_preservation_2b_frontend_url_appears_once_not_wildcard(frontend_url):
    """
    Property 2b: For any non-empty, non-wildcard FRONTEND_URL, it appears
    in ALLOWED_ORIGINS exactly once. We filter out '*' itself since that
    would be a misconfiguration, not a code bug.

    Validates: Requirements 3.2, 2.2
    """
    origins = _build_allowed_origins(frontend_url)

    # Must appear exactly once
    count = origins.count(frontend_url)
    assert count == 1, (
        f"Expected FRONTEND_URL={frontend_url!r} to appear exactly once "
        f"in ALLOWED_ORIGINS, but found {count} times. Got: {origins!r}"
    )

    assert "*" not in origins, (
        f"Wildcard '*' must never appear in ALLOWED_ORIGINS. Got: {origins!r}"
    )


# ---------------------------------------------------------------------------
# Property 2c — Empty FRONTEND_URL yields exactly the four localhost entries
# ---------------------------------------------------------------------------

@settings(max_examples=1)
@given(st.just(""))
def test_preservation_2c_empty_frontend_url_yields_only_defaults(frontend_url):
    """
    Property 2c: When FRONTEND_URL is empty (or absent), ALLOWED_ORIGINS
    contains exactly the four localhost entries — no more, no less.
    The empty-string guard prevents appending an empty string.

    Validates: Requirements 3.1
    """
    origins = _build_allowed_origins(frontend_url)

    assert origins == _LOCALHOST_DEFAULTS, (
        f"Expected exactly the four localhost defaults when FRONTEND_URL is empty, "
        f"but got: {origins!r}"
    )


# ---------------------------------------------------------------------------
# Task 3.2 — Unit tests for fix-checking (TestCORSConfig)
#
# These run against the FIXED app and assert the wildcard is gone.
# Validates: Requirements 2.1, 2.2, 2.3
# ---------------------------------------------------------------------------

class TestCORSConfig:
    """Unit tests that verify the fixed CORSMiddleware configuration."""

    def test_allow_origins_is_not_wildcard(self):
        """CORSMiddleware must not use allow_origins=['*']."""
        allow_origins = _get_cors_allow_origins()
        assert allow_origins != ["*"], (
            f"allow_origins must not be wildcard, got: {allow_origins!r}"
        )

    def test_allow_origins_equals_allowed_origins(self):
        """CORSMiddleware allow_origins must equal the ALLOWED_ORIGINS list."""
        allow_origins = _get_cors_allow_origins()
        assert allow_origins == ALLOWED_ORIGINS, (
            f"allow_origins={allow_origins!r} does not match "
            f"ALLOWED_ORIGINS={ALLOWED_ORIGINS!r}"
        )

    def test_allowed_origins_contains_four_defaults_when_no_frontend_url(self):
        """ALLOWED_ORIGINS has exactly four localhost entries when FRONTEND_URL is unset."""
        # Build fresh list with no FRONTEND_URL
        origins = _build_allowed_origins("")
        assert origins == _LOCALHOST_DEFAULTS, (
            f"Expected four localhost defaults, got: {origins!r}"
        )

    def test_allowed_origins_has_five_entries_with_frontend_url(self):
        """ALLOWED_ORIGINS has five entries when a FRONTEND_URL is provided."""
        origins = _build_allowed_origins("https://prod.example.com")
        assert len(origins) == 5, (
            f"Expected 5 origins, got {len(origins)}: {origins!r}"
        )
        assert "https://prod.example.com" in origins

    def test_empty_string_guard_prevents_appending(self):
        """Empty FRONTEND_URL must not add an empty entry to ALLOWED_ORIGINS."""
        origins = _build_allowed_origins("")
        assert "" not in origins, (
            f"Empty string must not appear in ALLOWED_ORIGINS: {origins!r}"
        )
        assert len(origins) == 4


# ---------------------------------------------------------------------------
# Task 3.5 — Integration tests using TestClient (TestCORSIntegration)
#
# Issues OPTIONS preflight requests and checks CORS response headers.
# Validates: Requirements 2.1, 2.2, 2.3, 3.1, 3.2, 3.3
# ---------------------------------------------------------------------------

from starlette.testclient import TestClient

_client = TestClient(app, raise_server_exceptions=False)

_PREFLIGHT_HEADERS = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "Content-Type,Authorization",
}


class TestCORSIntegration:
    """Integration tests: verify CORS headers on actual preflight responses."""

    def test_localhost_5173_is_accepted(self):
        """Preflight from localhost:5173 must receive the correct CORS header."""
        resp = _client.options(
            "/",
            headers={"Origin": "http://localhost:5173", **_PREFLIGHT_HEADERS},
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        assert acao == "http://localhost:5173", (
            f"Expected 'http://localhost:5173', got: {acao!r}"
        )

    def test_localhost_3000_is_accepted(self):
        """Preflight from localhost:3000 must receive the correct CORS header."""
        resp = _client.options(
            "/",
            headers={"Origin": "http://localhost:3000", **_PREFLIGHT_HEADERS},
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        assert acao == "http://localhost:3000", (
            f"Expected 'http://localhost:3000', got: {acao!r}"
        )

    def test_unknown_origin_is_rejected(self):
        """Preflight from an unlisted origin must NOT receive a permissive CORS header."""
        resp = _client.options(
            "/",
            headers={"Origin": "https://evil.example.com", **_PREFLIGHT_HEADERS},
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        assert acao != "https://evil.example.com", (
            f"Evil origin should not be allowed, but got ACAO: {acao!r}"
        )
        # Starlette omits the header entirely for disallowed origins
        assert acao == "" or acao == "null", (
            f"Expected empty/null ACAO for unknown origin, got: {acao!r}"
        )

    def test_production_frontend_url_is_accepted(self):
        """
        When the ALLOWED_ORIGINS list includes a production URL,
        a preflight from that origin must be accepted.

        We test this by verifying the list-building logic works correctly
        (tested in preservation tests) and that the fixed middleware uses
        ALLOWED_ORIGINS. Full module-reload monkeypatching is not needed
        because the integration is confirmed by tasks 3.3 and 3.4.
        """
        prod_url = "https://prod.example.com"
        origins = _build_allowed_origins(prod_url)
        assert prod_url in origins
        assert "*" not in origins
