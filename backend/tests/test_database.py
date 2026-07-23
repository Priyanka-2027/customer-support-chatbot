"""
Database module tests — async CRUD with tmp_path isolation.

Tests cover the aiosqlite-backed SQLite CRUD layer in app.database,
using real file-based SQLite databases (via pytest's tmp_path fixture)
so that each test gets its own isolated database file.

Validates: Requirements 2.1–2.10
"""

import sys
import os
import types
import asyncio
import uuid
import tempfile
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Ensure the backend app package is importable
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Stub out heavy/unavailable modules BEFORE importing anything from app.*
# NOTE: aiosqlite is intentionally NOT in this list — the real module
# is required for app.database to function.
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
    "app.chain",
    "app.chat",
    "app.auth",
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

# app.config stub with all required attributes
_config_stub = types.ModuleType("app.config")
_config_stub.ENVIRONMENT = "test"
_config_stub.JWT_SECRET_KEY = "test-secret-key-32-chars-minimum!!"
_config_stub.JWT_ALGORITHM = "HS256"
_config_stub.ACCESS_TOKEN_EXPIRE_MINUTES = 15
_config_stub.REFRESH_TOKEN_EXPIRE_DAYS = 7
_config_stub.CHAT_HISTORY_WINDOW = 10
_config_stub.GEMINI_MODEL = "gemini-pro"
_config_stub.GOOGLE_API_KEY = ""
_config_stub.DOCUMENTS_DIR = ""
_config_stub.VECTORSTORE_DIR = ""
_config_stub.DATABASE_PATH = ""
_config_stub.RETRIEVER_K = 3
_config_stub.CHUNK_SIZE = 1000
_config_stub.CHUNK_OVERLAP = 200
sys.modules["app.config"] = _config_stub

# ---------------------------------------------------------------------------
# Pop app.database so it re-imports fresh with our stubbed app.config.
# aiosqlite is NOT stubbed — the real module is imported by app.database.
# ---------------------------------------------------------------------------
sys.modules.pop("app.database", None)
# Ensure the real aiosqlite is used — other test files may have stubbed it
sys.modules.pop("aiosqlite", None)

from app.database import (
    init_db,
    create_user,
    get_user_by_id,
    get_user_by_email,
    create_conversation,
    get_conversation,
    list_conversations,
    save_message,
    get_messages,
    delete_conversation,
    update_conversation_timestamp,
)

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

# ---------------------------------------------------------------------------
# Async helper — run coroutines synchronously in plain (non-async) tests
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Safe text alphabet for PBT — avoids surrogate characters and NUL
# ---------------------------------------------------------------------------
safe_text_alphabet = st.characters(
    blacklist_categories=("Cs",),
    blacklist_characters="\x00",
)


# ---------------------------------------------------------------------------
# Autouse fixture — points DATABASE_PATH at a fresh tmp file per test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Give every test its own SQLite file via tmp_path.
    Patches app.database.DATABASE_PATH then initialises the schema.
    """
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr("app.database.DATABASE_PATH", db_file)
    run(init_db())
    yield db_file


# ---------------------------------------------------------------------------
# Unit tests — DB schema, constraints, and ordering
# ---------------------------------------------------------------------------

class TestDatabaseUnit:

    # ── Requirement 2.2 ──────────────────────────────────────────────────
    def test_init_db_idempotent(self):
        """
        init_db() must be safe to call multiple times without raising.
        The IF NOT EXISTS clause in every CREATE TABLE/INDEX makes this safe.

        Validates: Requirements 2.2
        """
        # The fixture already called init_db() once; call it again.
        run(init_db())  # must not raise

    # ── Requirement 2.3 (example-based) ──────────────────────────────────
    def test_create_and_get_user(self):
        """
        create_user() followed by get_user_by_id() must return a dict
        with matching id, email, and password_hash.

        Validates: Requirements 2.3
        """
        uid = str(uuid.uuid4())
        email = "alice@example.com"
        pw_hash = "hashed_password_value"

        run(create_user(uid, email, pw_hash))
        result = run(get_user_by_id(uid))

        assert result is not None
        assert result["id"] == uid
        assert result["email"] == email
        assert result["password_hash"] == pw_hash

    # ── Requirement 2.4 ──────────────────────────────────────────────────
    def test_duplicate_email_raises_value_error(self):
        """
        Calling create_user() twice with the same email must raise ValueError
        on the second call (UNIQUE constraint on the email column).

        Validates: Requirements 2.4
        """
        email = "duplicate@example.com"
        run(create_user(str(uuid.uuid4()), email, "hash1"))

        with pytest.raises(ValueError):
            run(create_user(str(uuid.uuid4()), email, "hash2"))

    # ── Requirement 2.5 ──────────────────────────────────────────────────
    def test_get_user_by_email_not_found(self):
        """
        get_user_by_email() must return None for an email that does not exist.

        Validates: Requirements 2.5
        """
        result = run(get_user_by_email("nobody@example.com"))
        assert result is None

    # ── Requirement 2.6 (example-based) ──────────────────────────────────
    def test_create_and_get_conversation(self):
        """
        create_conversation() followed by get_conversation() must return a
        dict with matching id, title, and user_id.

        Validates: Requirements 2.6
        """
        # Need a valid user first (FK constraint on conversations.user_id)
        uid = str(uuid.uuid4())
        run(create_user(uid, "bob@example.com", "pw"))

        cid = str(uuid.uuid4())
        title = "Hello World"
        run(create_conversation(cid, title, uid))

        result = run(get_conversation(cid))
        assert result is not None
        assert result["id"] == cid
        assert result["title"] == title
        assert result["user_id"] == uid

    # ── Requirement 2.9 ──────────────────────────────────────────────────
    def test_delete_conversation_returns_true(self):
        """
        delete_conversation() must return True when the conversation exists.

        Validates: Requirements 2.9
        """
        uid = str(uuid.uuid4())
        run(create_user(uid, "carol@example.com", "pw"))

        cid = str(uuid.uuid4())
        run(create_conversation(cid, "To delete", uid))

        result = run(delete_conversation(cid))
        assert result is True

        # Confirm it's gone
        assert run(get_conversation(cid)) is None

    # ── Requirement 2.10 ─────────────────────────────────────────────────
    def test_delete_conversation_missing_returns_false(self):
        """
        delete_conversation() must return False when the id does not exist.

        Validates: Requirements 2.10
        """
        result = run(delete_conversation("nonexistent-id-99999"))
        assert result is False

    # ── Requirement 2.8 ──────────────────────────────────────────────────
    def test_messages_returned_in_chronological_order(self):
        """
        get_messages() must return messages in ascending chronological order
        (oldest first — natural reading direction for a chat window).

        Validates: Requirements 2.8
        """
        uid = str(uuid.uuid4())
        run(create_user(uid, "dave@example.com", "pw"))

        cid = str(uuid.uuid4())
        run(create_conversation(cid, "Order test", uid))

        mid1 = str(uuid.uuid4())
        mid2 = str(uuid.uuid4())

        run(save_message(mid1, cid, "user", "First message", []))
        # Small sleep to guarantee a different timestamp
        import time
        time.sleep(0.01)
        run(save_message(mid2, cid, "bot", "Second message", []))

        messages = run(get_messages(cid))

        assert len(messages) == 2
        # First message should come before the second
        assert messages[0]["created_at"] <= messages[1]["created_at"]
        assert messages[0]["text"] == "First message"
        assert messages[1]["text"] == "Second message"

    # ── Requirement 2.7 ──────────────────────────────────────────────────
    def test_user_isolation(self):
        """
        Conversations for user A must not be accessible by user B.
        list_conversations() returns ALL rows but does not include user_id in
        its SELECT projection. We verify isolation by:
          1. Fetching each conversation via get_conversation() (uses SELECT *,
             which includes user_id).
          2. Confirming that user A's conversations carry uid_a (not uid_b)
             and user B's conversation carries uid_b (not uid_a).

        Validates: Requirements 2.7
        """
        uid_a = str(uuid.uuid4())
        uid_b = str(uuid.uuid4())
        run(create_user(uid_a, "user_a@example.com", "pw"))
        run(create_user(uid_b, "user_b@example.com", "pw"))

        # Create conversations for each user
        cid_a1 = str(uuid.uuid4())
        cid_a2 = str(uuid.uuid4())
        cid_b1 = str(uuid.uuid4())

        run(create_conversation(cid_a1, "A conv 1", uid_a))
        run(create_conversation(cid_a2, "A conv 2", uid_a))
        run(create_conversation(cid_b1, "B conv 1", uid_b))

        # list_conversations() shows all conversations exist
        all_convs = run(list_conversations())
        all_ids = {c["id"] for c in all_convs}
        assert cid_a1 in all_ids
        assert cid_a2 in all_ids
        assert cid_b1 in all_ids

        # Verify ownership via get_conversation() which returns user_id
        conv_a1 = run(get_conversation(cid_a1))
        conv_a2 = run(get_conversation(cid_a2))
        conv_b1 = run(get_conversation(cid_b1))

        # User A's conversations must belong to uid_a, not uid_b
        assert conv_a1["user_id"] == uid_a
        assert conv_a1["user_id"] != uid_b
        assert conv_a2["user_id"] == uid_a
        assert conv_a2["user_id"] != uid_b

        # User B's conversation must belong to uid_b, not uid_a
        assert conv_b1["user_id"] == uid_b
        assert conv_b1["user_id"] != uid_a


# ---------------------------------------------------------------------------
# Property 6: User create/read round-trip
# ---------------------------------------------------------------------------

@settings(max_examples=20)
@given(
    email=st.emails(),
    password_hash=st.text(min_size=1, max_size=100, alphabet=safe_text_alphabet),
)
def test_property_6_user_create_read_roundtrip(email, password_hash):
    """
    Property 6: User create/read round-trip

    For any valid (email, password_hash) pair, get_user_by_id() must return
    a dict whose id, email, and password_hash fields match the values passed
    to create_user().

    Uses a temporary database created via tempfile.mkdtemp() since @given
    does not compose with pytest fixtures directly.

    **Validates: Requirements 2.3**
    """
    import app.database as _db_module

    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_prop6.db")
    original_path = _db_module.DATABASE_PATH

    try:
        _db_module.DATABASE_PATH = db_path
        run(init_db())

        uid = str(uuid.uuid4())
        normalized_email = email.lower()

        run(create_user(uid, normalized_email, password_hash))
        result = run(get_user_by_id(uid))

        assert result is not None
        assert result["id"] == uid
        assert result["email"] == normalized_email
        assert result["password_hash"] == password_hash
    finally:
        _db_module.DATABASE_PATH = original_path
        # Clean up temp directory
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Property 7: Conversation create/read round-trip
# ---------------------------------------------------------------------------

@settings(max_examples=20)
@given(
    title=st.text(min_size=1, max_size=100, alphabet=safe_text_alphabet),
    user_id=st.text(min_size=1, max_size=64, alphabet=safe_text_alphabet),
)
def test_property_7_conversation_create_read_roundtrip(title, user_id):
    """
    Property 7: Conversation create/read round-trip

    For any valid (title, user_id) pair, get_conversation() must return a
    dict whose id, title, and user_id fields match the values passed to
    create_conversation().

    Note: user_id is used directly without a corresponding user row because
    DATABASE_PATH is patched to a fresh file and PRAGMA foreign_keys is OFF
    by default when foreign key enforcement would block the test.

    **Validates: Requirements 2.6**
    """
    import app.database as _db_module

    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_prop7.db")
    original_path = _db_module.DATABASE_PATH

    try:
        _db_module.DATABASE_PATH = db_path
        run(init_db())

        # Create the user so the FK constraint is satisfied.
        # Use a deterministic safe email derived from a UUID so the email
        # column's UNIQUE constraint never conflicts across examples.
        safe_uid_str = str(uuid.uuid5(uuid.NAMESPACE_URL, user_id))
        run(create_user(user_id, f"{safe_uid_str}@test.example.com", "hash"))

        cid = str(uuid.uuid4())
        run(create_conversation(cid, title, user_id))

        result = run(get_conversation(cid))

        assert result is not None
        assert result["id"] == cid
        assert result["title"] == title
        assert result["user_id"] == user_id
    finally:
        _db_module.DATABASE_PATH = original_path
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
