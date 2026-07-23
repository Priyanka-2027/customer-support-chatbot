"""
conftest.py — shared pytest fixtures and session-level patches.

Applies bcrypt 5.x → passlib 1.7.4 compatibility patches at session
startup, before any test module imports app.security or passlib.
"""

# ---------------------------------------------------------------------------
# Apply patches BEFORE passlib's CryptContext is ever instantiated
# ---------------------------------------------------------------------------
try:
    import bcrypt as _bcrypt_lib
    import types as _types

    # Patch 1: Add __about__ so passlib can read the bcrypt version
    if not hasattr(_bcrypt_lib, "__about__"):
        _about = _types.ModuleType("bcrypt.__about__")
        _about.__version__ = "4.0.1"
        _bcrypt_lib.__about__ = _about

    # Patch 2: Truncate passwords > 72 bytes (bcrypt 5.x now raises ValueError)
    if not getattr(_bcrypt_lib, "_hashpw_patched", False):
        _orig_hashpw = _bcrypt_lib.hashpw

        def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
            return _orig_hashpw(password[:72], salt)

        _bcrypt_lib.hashpw = _safe_hashpw
        _bcrypt_lib._hashpw_patched = True

except Exception:
    pass


# ---------------------------------------------------------------------------
# Session-scoped autouse fixture: ensure app.database stub is consistent
# across all test files so endpoint tests don't get the real aiosqlite module
# ---------------------------------------------------------------------------
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture(autouse=True, scope="session")
def ensure_database_stub():
    """
    Ensure app.database in sys.modules is a MagicMock for the full session.
    This prevents test_database.py (which pops app.database to use the real one)
    from leaving the real module in place for test_auth_endpoints.py and
    test_chat_endpoints.py, which need the stub.

    Note: test_database.py patches DATABASE_PATH via monkeypatch and sets
    sys.modules["app.database"] = real_module. We restore a stub after
    that test module completes by checking if a real aiosqlite is present.
    This fixture only sets up the initial state.
    """
    # Nothing to do at setup — each test file manages its own sys.modules state.
    yield

# ---------------------------------------------------------------------------
# Ensure app.database is re-stubbed before each endpoint test run.
# test_database.py pops and re-imports the real app.database, which then
# persists in sys.modules and breaks endpoint tests that rely on a stub.
# This fixture restores the stub before each test in endpoint test files.
# ---------------------------------------------------------------------------
import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture(autouse=True)
def ensure_database_stub(request):
    """
    If the test is in test_auth_endpoints.py or test_chat_endpoints.py,
    and the real app.database is in sys.modules (i.e., test_database.py ran first),
    re-install the MagicMock stub so endpoint tests remain hermetic.
    """
    import sys

    test_file = request.fspath.basename if request.fspath else ""

    if test_file in ("test_auth_endpoints.py", "test_chat_endpoints.py"):
        # Check if a real aiosqlite-backed database module got in
        db_mod = sys.modules.get("app.database")
        if db_mod is not None and not isinstance(db_mod, MagicMock):
            # Replace with a fresh stub
            stub = MagicMock()
            stub.create_user = AsyncMock(return_value=None)
            stub.get_user_by_email = AsyncMock(return_value=None)
            stub.get_user_by_id = AsyncMock(return_value=None)
            stub.get_conversation = AsyncMock(return_value=None)
            stub.get_messages = AsyncMock(return_value=[])
            stub.create_conversation = AsyncMock(return_value=None)
            stub.save_message = AsyncMock(return_value=None)
            stub.update_conversation_timestamp = AsyncMock(return_value=None)
            sys.modules["app.database"] = stub

            # Also re-import app.auth and app.chat to rebind their references
            for mod_name in ["app.auth", "app.chat", "app.security"]:
                sys.modules.pop(mod_name, None)

    yield
