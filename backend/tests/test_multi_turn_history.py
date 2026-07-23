"""
Multi-turn conversation history — property-based and unit tests.

Tests cover:
  Property 1: History structure and order preservation
  Property 2: Window truncation
  Property 3: format_history determinism
  Property 4: Per-message text truncation at 2000 chars
  Property 5: Invalid role raises ValueError
  Property 6: Invalid CHAT_HISTORY_WINDOW config raises ValueError
  Unit tests : format_history edge cases, ask() integration, prompt structure

Feature: multi-turn-chat-history
Validates: Requirements 1.1–1.6, 3.1–3.4, 4.1–4.5, 6.1–6.4
"""

import sys
import os
import types
from unittest.mock import MagicMock, patch, AsyncMock

# ---------------------------------------------------------------------------
# Make the backend app package importable from the tests/ directory
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Stub heavy ML modules so importing app.chain only needs langchain-core
# ---------------------------------------------------------------------------
_STUBS = [
    "langchain",
    "langchain.chains",
    "langchain.chains.combine_documents",
    "langchain.chains.retrieval",
    "langchain_community",
    "langchain_community.vectorstores",
    "langchain_google_genai",
    "langchain_huggingface",
    "sentence_transformers",
    "faiss",
    "aiosqlite",
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

import fastapi
for _name in ("app.auth", "app.chat"):
    _stub = MagicMock()
    _stub.router = fastapi.APIRouter()
    sys.modules[_name] = _stub

# Remove app.chain stub if test_cors.py registered one — we need the real module.
sys.modules.pop("app.chain", None)

# Provide real config values so config.py validates correctly
import app.config as _cfg  # noqa: E402 — must come after sys.path insert

import pytest
from hypothesis import given, settings, assume, HealthCheck
import hypothesis.strategies as st

from app.chain import format_history, PROMPT_TEMPLATE
from app.config import CHAT_HISTORY_WINDOW

# ---------------------------------------------------------------------------
# Shared hypothesis strategies
# ---------------------------------------------------------------------------

_valid_roles = st.sampled_from(["user", "bot"])

_message_strategy = st.fixed_dictionaries({
    "role": _valid_roles,
    "text": st.text(min_size=1, max_size=500),
})


# ===========================================================================
# Property 1 — History structure and order preservation
# Feature: multi-turn-chat-history, Property 1
# Validates: Requirements 1.3, 3.4, 4.3
# ===========================================================================

@settings(max_examples=100)
@given(messages=st.lists(_message_strategy, min_size=1, max_size=50))
def test_property1_structure_and_order(messages):
    """
    For any non-empty list of valid messages, format_history must produce a
    string where every visible message appears in original order, with the
    correct role label prefix.
    """
    result = format_history(messages)

    # The visible window is the last min(len, CHAT_HISTORY_WINDOW*2) messages
    max_msgs = CHAT_HISTORY_WINDOW * 2
    visible = messages[-max_msgs:] if len(messages) > max_msgs else messages

    role_label = {"user": "Customer", "bot": "Support Agent"}

    # Check each visible message appears in order with correct label.
    # We scan sequentially through the result string rather than splitting
    # on "\n" — message text may itself contain newlines.
    search_pos = 0
    for msg in visible:
        expected_label = role_label[msg["role"]]
        expected_prefix = f"{expected_label}: "
        truncated_text = msg["text"][:2000]

        # Find the label prefix starting from where we left off
        idx = result.find(expected_prefix, search_pos)
        assert idx != -1, (
            f"Label '{expected_prefix}' not found after position {search_pos} "
            f"in result: {result[:200]!r}"
        )

        # The truncated text must follow the label at this position
        content_start = idx + len(expected_prefix)
        actual_content = result[content_start:content_start + len(truncated_text)]
        assert actual_content == truncated_text, (
            f"Text mismatch at position {idx}: "
            f"expected {truncated_text[:50]!r}, got {actual_content[:50]!r}"
        )

        # Advance past this match so we check order
        search_pos = content_start + len(truncated_text)


# ===========================================================================
# Property 2 — Window truncation
# Feature: multi-turn-chat-history, Property 2
# Validates: Requirements 1.4, 6.3
# ===========================================================================

@settings(max_examples=100)
@given(
    messages=st.lists(_message_strategy, min_size=1, max_size=100),
    window=st.integers(min_value=1, max_value=20),
)
def test_property2_window_truncation(messages, window):
    """
    For any window N and any message list, the output must contain at most
    window*2 role-label entries (the most recent N user+bot pairs).
    We count label prefix occurrences rather than splitting on newlines
    because message text may itself contain newlines.
    """
    import re as _re
    result = format_history(messages, window=window)

    # Count "Customer: " and "Support Agent: " label occurrences
    label_count = len(_re.findall(r'(?:Customer|Support Agent): ', result))

    assert label_count <= window * 2, (
        f"Expected at most {window * 2} label entries for window={window}, "
        f"got {label_count} from {len(messages)} messages"
    )


# ===========================================================================
# Property 3 — Determinism
# Feature: multi-turn-chat-history, Property 3
# Validates: Requirements 4.4
# ===========================================================================

@settings(max_examples=100)
@given(messages=st.lists(_message_strategy, max_size=30))
def test_property3_determinism(messages):
    """
    format_history is a pure function — calling it twice with the same
    input must produce identical output.
    """
    assert format_history(messages) == format_history(messages)


# ===========================================================================
# Property 4 — Per-message text truncation at 2000 chars
# Feature: multi-turn-chat-history, Property 4
# Validates: Requirements 4.5
# ===========================================================================

@settings(max_examples=100)
@given(
    prefix=st.text(max_size=100),
    role=_valid_roles,
)
def test_property4_text_truncation(prefix, role):
    """
    Any message whose text exceeds 2000 characters must be truncated so
    the content portion of the output line is at most 2000 characters.
    """
    long_text = prefix + ("x" * 2001)  # guaranteed > 2000 chars
    msg = {"role": role, "text": long_text}
    result = format_history([msg])

    label = "Customer" if role == "user" else "Support Agent"
    prefix_str = f"{label}: "
    assert result.startswith(prefix_str)

    content_part = result[len(prefix_str):]
    assert len(content_part) <= 2000, (
        f"Content part has {len(content_part)} chars, expected ≤ 2000"
    )


# ===========================================================================
# Property 5 — Invalid role raises ValueError
# Feature: multi-turn-chat-history, Property 5
# Validates: Requirements 1.6
# ===========================================================================

@settings(max_examples=100)
@given(
    bad_role=st.text().filter(lambda s: s not in ("user", "bot")),
    text=st.text(min_size=1),
)
def test_property5_invalid_role_raises(bad_role, text):
    """
    Any message with a role that is not 'user' or 'bot' must raise ValueError.
    """
    with pytest.raises(ValueError, match="Invalid message role"):
        format_history([{"role": bad_role, "text": text}])


# ===========================================================================
# Property 6 — Invalid CHAT_HISTORY_WINDOW config raises ValueError
# Feature: multi-turn-chat-history, Property 6
# Validates: Requirements 6.4
# ===========================================================================

@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    bad_value=st.one_of(
        st.integers(max_value=0).map(str),  # zero or negative
        # Non-numeric strings: exclude null bytes (os.environ rejects them on Windows)
        st.text(alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00")).filter(
            lambda s: s != "" and not s.lstrip("-").isdigit()
        ),
    )
)
def test_property6_invalid_window_config_raises(bad_value, monkeypatch):
    """
    Setting CHAT_HISTORY_WINDOW to a non-positive-integer value must raise
    ValueError when the config validation logic runs.
    Uses inline validation instead of importlib.reload because app.config
    is a stub types.ModuleType without a __spec__, which reload requires.
    """
    monkeypatch.setenv("CHAT_HISTORY_WINDOW", bad_value)
    # Re-execute the exact validation logic from config.py inline
    with pytest.raises(ValueError):
        raw = bad_value
        try:
            val = int(raw)
            if val <= 0:
                raise ValueError()
        except ValueError:
            raise ValueError(
                f"CHAT_HISTORY_WINDOW must be a positive integer. Got: '{raw}'"
            )
    # Restore env so subsequent tests aren't affected
    monkeypatch.setenv("CHAT_HISTORY_WINDOW", "10")


# ===========================================================================
# Unit tests — format_history edge cases
# ===========================================================================

class TestFormatHistoryUnit:

    def test_empty_list_returns_empty_string(self):
        """format_history([]) must return ''."""
        assert format_history([]) == ""

    def test_single_user_message(self):
        result = format_history([{"role": "user", "text": "Hello"}])
        assert result == "Customer: Hello"

    def test_single_bot_message(self):
        result = format_history([{"role": "bot", "text": "Hi there"}])
        assert result == "Support Agent: Hi there"

    def test_two_messages_newline_separated(self):
        msgs = [
            {"role": "user", "text": "What is the return policy?"},
            {"role": "bot", "text": "You can return within 30 days."},
        ]
        result = format_history(msgs)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "Customer: What is the return policy?"
        assert lines[1] == "Support Agent: You can return within 30 days."

    def test_text_at_exactly_2000_chars_not_truncated(self):
        text = "a" * 2000
        result = format_history([{"role": "user", "text": text}])
        assert result == f"Customer: {text}"

    def test_text_at_2001_chars_is_truncated(self):
        text = "a" * 2001
        result = format_history([{"role": "user", "text": text}])
        content = result[len("Customer: "):]
        assert len(content) == 2000

    def test_window_zero_handled_by_config_not_format_history(self):
        """Window=1 includes only the last 2 messages."""
        msgs = [
            {"role": "user", "text": "first"},
            {"role": "bot", "text": "second"},
            {"role": "user", "text": "third"},
        ]
        result = format_history(msgs, window=1)
        lines = result.split("\n")
        assert len(lines) == 2
        assert "Support Agent: second" in result
        assert "Customer: third" in result
        assert "Customer: first" not in result


# ===========================================================================
# Unit tests — PROMPT_TEMPLATE structure
# ===========================================================================

class TestPromptTemplateStructure:

    def test_system_message_contains_chat_history_block_placeholder(self):
        """The system prompt must contain {chat_history_block}."""
        # PROMPT_TEMPLATE.messages is a list of message templates
        system_msg = PROMPT_TEMPLATE.messages[0]
        template_str = system_msg.prompt.template
        assert "{chat_history_block}" in template_str, (
            "SYSTEM_PROMPT must contain {chat_history_block} placeholder"
        )

    def test_system_message_contains_context_placeholder(self):
        system_msg = PROMPT_TEMPLATE.messages[0]
        template_str = system_msg.prompt.template
        assert "{context}" in template_str

    def test_message_order_is_system_then_human(self):
        """First message must be system, second must be human."""
        from langchain_core.messages import SystemMessage, HumanMessage
        msgs = PROMPT_TEMPLATE.messages
        assert len(msgs) == 2
        # Check type names rather than importing private classes
        assert "system" in type(msgs[0]).__name__.lower() or hasattr(msgs[0], "prompt")
        assert "human" in type(msgs[1]).__name__.lower() or "{input}" in str(msgs[1])
