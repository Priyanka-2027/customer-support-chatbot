# database.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   All SQLite database operations for chat history.
#   Provides an async context manager for connections and
#   functions for every CRUD operation the API needs.
#
# Why SQLite?
#   - Zero infrastructure — a single file on disk
#   - No separate server process to manage or pay for
#   - Works identically in development and on Render's free tier
#   - aiosqlite wraps it with async/await so it never blocks
#     FastAPI's event loop
#   - Sufficient for hundreds of thousands of conversations
#
# Schema:
#   conversations(id, title, created_at, updated_at)
#   messages(id, conversation_id, role, text, sources, created_at)
# ─────────────────────────────────────────────────────────────

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import aiosqlite

from app.config import DATABASE_PATH

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# get_db()  — async context manager for database connections
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that yields a database connection.

    Usage:
        async with get_db() as db:
            await db.execute(...)

    Why a context manager?
        Connections are expensive resources. Using a context manager
        guarantees the connection is closed after each operation,
        even if an exception is raised. No connection leaks.

    Why not a connection pool?
        SQLite supports only one writer at a time anyway. A single
        connection per request is the correct pattern for SQLite.
        For PostgreSQL you would use asyncpg with a pool.
    """
    # aiosqlite.connect() opens an async connection to the SQLite
    # file at DATABASE_PATH. If the file doesn't exist, SQLite
    # creates it automatically — no manual setup required.
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:

        # row_factory = aiosqlite.Row makes rows behave like dicts:
        #   row["id"] instead of row[0]
        # This is safer and more readable than positional indexing.
        db.row_factory = aiosqlite.Row

        # WAL (Write-Ahead Logging) mode improves concurrent read
        # performance. Readers don't block writers and vice versa.
        # Essential when FastAPI handles multiple requests at once.
        await db.execute("PRAGMA journal_mode=WAL")

        # foreign_keys=ON enforces FK constraints in SQLite.
        # By default SQLite parses but ignores FK constraints —
        # this pragma enables actual enforcement so deleting a
        # conversation cascades to delete its messages.
        await db.execute("PRAGMA foreign_keys=ON")

        yield db


# ─────────────────────────────────────────────────────────────
# init_db()  — create tables if they don't exist
# ─────────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Create the database schema on first run.
    Called once at application startup. IF NOT EXISTS makes it
    safe to call on every restart.
    """
    async with get_db() as db:

        # ── users table ────────────────────────────────────────
        # Stores registered accounts.
        # password_hash: bcrypt hash — never the plain password.
        # email is UNIQUE so duplicate registrations are rejected
        # at the database level, not just in application code.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            )
        """)

        # Index on email for O(log n) login lookups.
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email
            ON users(email)
        """)

        # ── conversations table ────────────────────────────────
        # Now includes user_id so conversations are per-user.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                title       TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── messages table ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id               TEXT PRIMARY KEY,
                conversation_id  TEXT NOT NULL,
                role             TEXT NOT NULL CHECK(role IN ('user','bot')),
                text             TEXT NOT NULL,
                sources          TEXT NOT NULL DEFAULT '[]',
                created_at       TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_messages_conversation_id
            ON messages(conversation_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_conversations_updated_at
            ON conversations(updated_at DESC)
        """)

        # Index conversations by user_id so listing a user's
        # conversations is O(log n) instead of a full table scan.
        await db.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_conversations_user_id
            ON conversations(user_id)
        """)

        await db.commit()

    logger.info(f"Database initialised at: {DATABASE_PATH}")


# ─────────────────────────────────────────────────────────────
# User operations
# ─────────────────────────────────────────────────────────────

async def create_user(user_id: str, email: str, password_hash: str) -> dict:
    """
    Insert a new user row. Raises ValueError if email already exists.

    Args:
        user_id:       UUID string.
        email:         Lowercase email address.
        password_hash: bcrypt hash of the plaintext password.

    Returns:
        dict with id, email, created_at.

    Raises:
        ValueError: If the email is already registered.
    """
    now = _utcnow()

    async with get_db() as db:
        try:
            await db.execute(
                """
                INSERT INTO users (id, email, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, email, password_hash, now),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            # UNIQUE constraint on email — duplicate registration.
            # We raise ValueError here and let the route handler
            # convert it to the right HTTP status code.
            raise ValueError(f"Email '{email}' is already registered.")

    return {"id": user_id, "email": email, "created_at": now}


async def get_user_by_email(email: str) -> dict | None:
    """
    Look up a user by email address.

    Used during login to verify credentials.

    Args:
        email: The email to look up (should be lowercased by caller).

    Returns:
        dict with id, email, password_hash, created_at — or None.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ) as cursor:
            row = await cursor.fetchone()

    return dict(row) if row else None


async def get_user_by_id(user_id: str) -> dict | None:
    """
    Look up a user by their UUID.

    Used when validating JWT tokens — the token carries the user_id
    as the 'sub' (subject) claim. We verify the user still exists.

    Args:
        user_id: The UUID string from the JWT 'sub' claim.

    Returns:
        dict or None.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────
# Conversation operations
# ─────────────────────────────────────────────────────────────

async def create_conversation(
    conversation_id: str,
    title: str,
    user_id: str,
) -> dict:
    """
    Insert a new conversation row owned by a specific user.

    Args:
        conversation_id: UUID string.
        title:           First 60 chars of the opening question.
        user_id:         The user who owns this conversation.

    Returns:
        dict with id, user_id, title, created_at, updated_at.
    """
    now = _utcnow()

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO conversations (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, user_id, title, now, now),
        )
        await db.commit()

    return {
        "id": conversation_id,
        "user_id": user_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }


async def list_conversations() -> list[dict]:
    """
    Return all conversations ordered by most recently updated.

    The sidebar shows this list — most recent at the top.

    Returns:
        List of dicts with id, title, updated_at, and
        message_count (total messages in that conversation).
    """
    async with get_db() as db:
        # LEFT JOIN with COUNT so conversations with no messages
        # still appear (count = 0) rather than being hidden.
        async with db.execute("""
            SELECT
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        """) as cursor:
            rows = await cursor.fetchall()

    # Convert aiosqlite.Row objects to plain dicts.
    # dict(row) works because row_factory = aiosqlite.Row
    # makes rows behave like mappings.
    return [dict(row) for row in rows]


async def get_conversation(conversation_id: str) -> dict | None:
    """
    Return a single conversation by id, or None if not found.

    Args:
        conversation_id: The UUID of the conversation.

    Returns:
        dict or None.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        ) as cursor:
            row = await cursor.fetchone()

    return dict(row) if row else None


async def update_conversation_timestamp(conversation_id: str) -> None:
    """
    Update updated_at to now for a conversation.

    Called after every new message is saved so the sidebar
    keeps conversations sorted by activity correctly.

    Args:
        conversation_id: The UUID of the conversation to touch.
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_utcnow(), conversation_id),
        )
        await db.commit()


async def delete_conversation(conversation_id: str) -> bool:
    """
    Delete a conversation and all its messages.

    The ON DELETE CASCADE on the messages table means deleting
    the conversation row automatically deletes all message rows
    with that conversation_id — no second DELETE needed.

    Args:
        conversation_id: The UUID of the conversation to delete.

    Returns:
        True if a row was deleted, False if id was not found.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()

        # cursor.rowcount is -1 if no rows were affected (id not found).
        # 1 means the delete succeeded.
        return cursor.rowcount == 1


# ─────────────────────────────────────────────────────────────
# Message operations
# ─────────────────────────────────────────────────────────────

async def save_message(
    message_id: str,
    conversation_id: str,
    role: str,
    text: str,
    sources: list,
) -> dict:
    """
    Insert one message row into the database.

    Args:
        message_id:      UUID for the message.
        conversation_id: Which conversation this belongs to.
        role:            "user" or "bot".
        text:            The message content.
        sources:         List of SourceDocument dicts (may be empty).

    Returns:
        dict representation of the saved message.
    """
    now = _utcnow()

    # sources is a Python list of dicts. SQLite has no native JSON
    # column type, so we serialise to a JSON string for storage.
    # json.dumps([]) produces "[]" for empty lists — always a
    # valid JSON string, never NULL.
    sources_json: str = json.dumps(sources)

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, text, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, conversation_id, role, text, sources_json, now),
        )
        await db.commit()

    return {
        "id": message_id,
        "conversation_id": conversation_id,
        "role": role,
        "text": text,
        "sources": sources,   # return the list, not the JSON string
        "created_at": now,
    }


async def get_messages(conversation_id: str) -> list[dict]:
    """
    Return all messages for a conversation, oldest first.

    ORDER BY created_at ASC preserves the chronological order
    of the conversation — newest messages appear last in the
    chat window, which is the natural reading direction.

    Args:
        conversation_id: The UUID of the conversation.

    Returns:
        List of message dicts with sources already deserialised.
    """
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    messages = []
    for row in rows:
        msg = dict(row)

        # Deserialise the sources JSON string back into a Python list.
        # json.loads("[]") → []  so this is always safe.
        msg["sources"] = json.loads(msg["sources"])

        messages.append(msg)

    return messages


# ─────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────

def _utcnow() -> str:
    """
    Return the current UTC time as an ISO-8601 string.

    Example: "2024-01-15T10:23:01.456789+00:00"

    Using UTC everywhere prevents timezone confusion — all
    timestamps in the database are in the same reference frame,
    regardless of where the server is deployed.

    datetime.now(timezone.utc) is the correct modern Python way
    to get timezone-aware UTC time. datetime.utcnow() is deprecated
    in Python 3.12 because it returns a naive datetime.
    """
    return datetime.now(timezone.utc).isoformat()
