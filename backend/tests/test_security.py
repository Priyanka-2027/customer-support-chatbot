"""
Security tests for the FastAPI backend — bcrypt + JWT.

Validates password hashing/verification (bcrypt) and JWT token
creation/decoding (access and refresh tokens) using property-based
and example-based tests.

Validates: Requirements 1.1–1.10
"""

import sys
import os
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Ensure the backend app package is importable
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Stub out heavy/unavailable modules BEFORE importing anything from app.*
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

# app.config stub with all required attributes
_config_stub = types.ModuleType("app.config")
_config_stub.JWT_SECRET_KEY = "test-secret-key-32-chars-minimum!!"
_config_stub.JWT_ALGORITHM = "HS256"
_config_stub.ACCESS_TOKEN_EXPIRE_MINUTES = 15
_config_stub.REFRESH_TOKEN_EXPIRE_DAYS = 7
_config_stub.CHAT_HISTORY_WINDOW = 10
_config_stub.GEMINI_MODEL = "gemini-pro"
_config_stub.GOOGLE_API_KEY = ""
_config_stub.ENVIRONMENT = "test"
_config_stub.DOCUMENTS_DIR = ""
_config_stub.VECTORSTORE_DIR = ""
_config_stub.DATABASE_PATH = ""
_config_stub.RETRIEVER_K = 3
_config_stub.CHUNK_SIZE = 1000
_config_stub.CHUNK_OVERLAP = 200
sys.modules["app.config"] = _config_stub

# ---------------------------------------------------------------------------
# Fix passlib 1.7.4 + bcrypt 5.x incompatibility.
#
# passlib's detect_wrap_bug() (called during bcrypt backend initialization)
# uses a 255-byte test password. bcrypt 5.x now raises ValueError for
# passwords >72 bytes instead of silently truncating, breaking passlib's
# detection logic before any real hashing can happen.
#
# Fix: patch bcrypt.hashpw to silently truncate to 72 bytes, matching
# historical bcrypt behavior (bcrypt has always only used the first 72 bytes).
# ---------------------------------------------------------------------------
try:
    import bcrypt as _bcrypt_lib
    _original_hashpw = _bcrypt_lib.hashpw

    def _patched_hashpw(password: bytes, salt: bytes) -> bytes:
        return _original_hashpw(password[:72], salt)

    _bcrypt_lib.hashpw = _patched_hashpw
except Exception:
    pass  # If patching fails, tests will surface the real error

# ---------------------------------------------------------------------------
# Fix passlib 1.7.4 + bcrypt 5.x incompatibility (applied globally via conftest.py,
# but also here for when this file is run in isolation)
# ---------------------------------------------------------------------------
try:
    import bcrypt as _bcrypt_lib
    import types as _types

    if not hasattr(_bcrypt_lib, "__about__"):
        _about = _types.ModuleType("bcrypt.__about__")
        _about.__version__ = "4.0.1"
        _bcrypt_lib.__about__ = _about

    if not getattr(_bcrypt_lib, "_hashpw_patched", False):
        _orig_hashpw = _bcrypt_lib.hashpw
        def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
            return _orig_hashpw(password[:72], salt)
        _bcrypt_lib.hashpw = _safe_hashpw
        _bcrypt_lib._hashpw_patched = True
except Exception:
    pass

# Pop app.security so it re-imports fresh with our stubbed app.config
sys.modules.pop("app.security", None)

from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

# ---------------------------------------------------------------------------
# Speed up tests — no-op since we now use direct bcrypt (no work factor setting)
# ---------------------------------------------------------------------------
import pytest
from fastapi import HTTPException
from hypothesis import given, settings
import hypothesis.strategies as st

# ---------------------------------------------------------------------------
# PBT strategies
# ---------------------------------------------------------------------------

# bcrypt has a 72-byte limit on password input. We use ASCII-only alphabet
# to ensure character count == byte count, avoiding multi-byte UTF-8 issues.
_password_strategy = st.text(
    min_size=1,
    max_size=72,
    alphabet=st.characters(
        min_codepoint=33,  # ASCII printable starting from '!'
        max_codepoint=126,  # ASCII printable ending at '~'
    ),
)

_user_id_strategy = st.text(
    min_size=1,
    max_size=64,
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="\x00",
    ),
)


# ---------------------------------------------------------------------------
# Property 1: Password hash/verify round-trip
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None)
@given(_password_strategy)
def test_property_1_password_hash_verify_roundtrip(p):
    """
    Property 1: Password hash/verify round-trip

    For any non-empty password, verify_password(p, hash_password(p)) is True.

    **Validates: Requirements 1.2**
    """
    assert verify_password(p, hash_password(p)) is True


# ---------------------------------------------------------------------------
# Property 2: bcrypt random-salt uniqueness
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None)
@given(_password_strategy)
def test_property_2_bcrypt_unique_hashes(p):
    """
    Property 2: bcrypt random-salt uniqueness

    Two consecutive calls to hash_password with the same password must
    produce different hashes because bcrypt generates a random salt each time.

    **Validates: Requirements 1.3**
    """
    assert hash_password(p) != hash_password(p)


# ---------------------------------------------------------------------------
# Property 3: Wrong-password rejection
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None)
@given(_password_strategy, _password_strategy)
def test_property_3_wrong_password_rejected(p1, p2):
    """
    Property 3: Wrong-password rejection

    For any two distinct passwords, verify_password(p1, hash_password(p2))
    must return False.

    **Validates: Requirements 1.4**
    """
    # Only test when passwords are genuinely different
    if p1 == p2:
        return
    assert verify_password(p1, hash_password(p2)) is False


# ---------------------------------------------------------------------------
# Property 4: Access-token JWT round-trip
# ---------------------------------------------------------------------------

@settings(max_examples=50)
@given(_user_id_strategy)
def test_property_4_access_token_roundtrip(uid):
    """
    Property 4: Access-token JWT round-trip

    For any user ID, decode_token(create_access_token(uid), "access") == uid.

    **Validates: Requirements 1.5**
    """
    token = create_access_token(uid)
    assert decode_token(token, "access") == uid


# ---------------------------------------------------------------------------
# Property 5: Refresh-token JWT round-trip
# ---------------------------------------------------------------------------

@settings(max_examples=50)
@given(_user_id_strategy)
def test_property_5_refresh_token_roundtrip(uid):
    """
    Property 5: Refresh-token JWT round-trip

    For any user ID, decode_token(create_refresh_token(uid), "refresh") == uid.

    **Validates: Requirements 1.6**
    """
    token = create_refresh_token(uid)
    assert decode_token(token, "refresh") == uid


# ---------------------------------------------------------------------------
# Unit tests: token-type enforcement and edge cases
# ---------------------------------------------------------------------------

class TestTokenTypeEnforcement:
    """Unit tests for token-type cross-use rejection and edge cases."""

    def test_access_token_rejected_as_refresh(self):
        """
        An access token must NOT be accepted where a refresh token is expected.

        Validates: Requirements 1.7
        """
        token = create_access_token("user-123")
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, "refresh")
        assert exc_info.value.status_code == 401

    def test_refresh_token_rejected_as_access(self):
        """
        A refresh token must NOT be accepted where an access token is expected.

        Validates: Requirements 1.8
        """
        token = create_refresh_token("user-123")
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, "access")
        assert exc_info.value.status_code == 401

    def test_expired_token_rejected(self):
        """
        A token with exp in the past must be rejected with HTTPException(401).

        Validates: Requirements 1.9
        """
        from jose import jwt as jose_jwt

        past_exp = datetime.now(timezone.utc) - timedelta(seconds=1)
        payload = {
            "sub": "user-123",
            "type": "access",
            "exp": past_exp,
        }
        expired_token = jose_jwt.encode(
            payload,
            _config_stub.JWT_SECRET_KEY,
            algorithm=_config_stub.JWT_ALGORITHM,
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_token(expired_token, "access")
        assert exc_info.value.status_code == 401

    def test_invalid_jwt_string_rejected(self):
        """
        A malformed/non-JWT string must be rejected with HTTPException(401).

        Validates: Requirements 1.10
        """
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.jwt", "access")
        assert exc_info.value.status_code == 401
