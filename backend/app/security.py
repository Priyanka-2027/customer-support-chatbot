# security.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   All cryptographic operations:
#     - Password hashing and verification (bcrypt)
#     - JWT access token creation and decoding
#     - JWT refresh token creation and decoding
#     - FastAPI dependency that extracts + validates the current user
#
# Nothing in this file does I/O (no DB calls, no HTTP calls).
# It only works with strings and dicts.
# This makes it easy to test in isolation.
# ─────────────────────────────────────────────────────────────

import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt as _bcrypt

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Password hashing — bcrypt directly (bypasses passlib's 72-byte check
# which is incompatible with bcrypt 4.x on Python 3.14)
# ─────────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password with bcrypt.

    Uses bcrypt directly rather than passlib to avoid the passlib/bcrypt 4.x
    compatibility issue on Python 3.14. Passwords are truncated to 72 bytes
    (bcrypt's natural limit) before hashing — this is safe and standard.

    Args:
        plain_password: The raw password string from the user.

    Returns:
        bcrypt hash string (bytes decoded to str) safe to store in the database.
    """
    password_bytes = plain_password.encode("utf-8")[:72]
    hashed = _bcrypt.hashpw(password_bytes, _bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    Args:
        plain_password:   The raw password from the login form.
        hashed_password:  The bcrypt hash stored in the database.

    Returns:
        True if the password matches, False otherwise.
    """
    password_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return _bcrypt.checkpw(password_bytes, hash_bytes)


# ─────────────────────────────────────────────────────────────
# JWT token creation
# ─────────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    """
    Create a short-lived JWT access token for a user.

    The token is signed with JWT_SECRET_KEY using HS256.
    The signature prevents tampering — if any part of the
    payload is modified, the signature check fails.

    Payload (claims) included:
      sub  — subject — the user's UUID (standard JWT claim)
      type — "access" — prevents an access token from being
             used where a refresh token is expected
      exp  — expiry time (standard JWT claim, checked by jose)
      iat  — issued-at time for audit purposes

    Args:
        user_id: The UUID of the authenticated user.

    Returns:
        A signed JWT string to send to the client.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,           # subject — who this token is for
        "type": "access",         # token type guard
        "exp": expire,            # jose checks this automatically on decode
        "iat": now,               # issued-at — useful for audit logs
    }

    # jwt.encode() signs the payload with the secret key and
    # returns the compact JWT string: header.payload.signature
    # All three parts are base64url-encoded, not encrypted —
    # the payload is readable but not modifiable without the key.
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """
    Create a long-lived JWT refresh token for a user.

    Refresh tokens have a longer lifetime (7 days) and are only
    accepted by the POST /auth/refresh endpoint.
    They are NOT accepted on protected API endpoints.

    The 'type': 'refresh' claim enforces this separation —
    get_current_user() rejects refresh tokens, and the refresh
    endpoint rejects access tokens.

    Args:
        user_id: The UUID of the authenticated user.

    Returns:
        A signed JWT string for the client to store.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str) -> str:
    """
    Decode and validate a JWT token. Return the user_id on success.

    Validates:
      1. Signature — was this token signed by our secret key?
      2. Expiry    — has exp passed? (jose raises ExpiredSignatureError)
      3. Type      — does 'type' claim match expected_type?

    Args:
        token:         The raw JWT string from the Authorization header.
        expected_type: "access" or "refresh".

    Returns:
        The user UUID from the 'sub' claim.

    Raises:
        HTTPException 401 if the token is invalid, expired, or wrong type.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        # WWW-Authenticate header tells the client which auth scheme
        # the server expects. Required by the OAuth2 spec.
        headers={"WWW-Authenticate": "Bearer"},
        detail="Could not validate credentials.",
    )

    try:
        # jwt.decode() verifies the signature AND checks exp automatically.
        # If exp has passed, jose raises ExpiredSignatureError (subclass of JWTError).
        # algorithms=[...] is a list — we only accept HS256.
        # Never pass algorithms=None; that would accept any algorithm
        # including 'none', which has no signature at all.
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Extract the user ID from the 'sub' claim.
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception

        # Verify the token type matches what the caller expects.
        # This prevents using a refresh token on a protected endpoint
        # or vice versa.
        token_type: str | None = payload.get("type")
        if token_type != expected_type:
            raise credentials_exception

        return user_id

    except JWTError:
        # JWTError covers: invalid signature, expired token,
        # malformed token, wrong algorithm. We don't leak which
        # specific check failed — always return the same 401.
        raise credentials_exception


# ─────────────────────────────────────────────────────────────
# FastAPI dependency — extract current user from request
# ─────────────────────────────────────────────────────────────

# OAuth2PasswordBearer defines the security scheme for OpenAPI docs.
# tokenUrl is the endpoint where clients exchange credentials for tokens.
# FastAPI uses this to show a "Authorize" button in /docs.
#
# auto_error=False means FastAPI returns None (instead of raising 401)
# when the Authorization header is absent. This allows the cookie path
# to serve as the primary authentication mechanism while still supporting
# Bearer tokens for Swagger UI (/docs) compatibility.
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


async def get_current_user(
    request: Request,
    bearer: str | None = Depends(oauth2_scheme_optional),
) -> dict:
    """
    FastAPI dependency — validates the JWT and returns the user dict.

    Used as Depends(get_current_user) on any protected endpoint:

        @router.post("/chat")
        async def chat(
            request: ChatRequestWithHistory,
            current_user: dict = Depends(get_current_user),
        ):
            user_id = current_user["id"]

    Flow:
      1. Try to read the access_token from the HttpOnly cookie (primary path)
      2. Fall back to the Authorization: Bearer header (Swagger UI / API clients)
      3. Raise 401 if neither source yields a token
      4. decode_token() verifies signature, expiry, and type
      5. We look up the user in the database to confirm they
         still exist (handles account deletion mid-session)
      6. Return the full user dict

    Args:
        request: The incoming HTTP request (provides access to cookies).
        bearer:  Bearer token from Authorization header, or None if absent.

    Returns:
        User dict with id, email, created_at.

    Raises:
        HTTPException 401 if no token is present, the token is invalid,
        or the user no longer exists.
    """
    # Import here to avoid circular imports — security.py ← database.py ← config.py
    from app.database import get_user_by_id

    # 1. Try cookie first (primary path for browser clients)
    token = request.cookies.get("access_token")

    # 2. Fall back to Bearer header (for Swagger UI and API clients)
    if not token:
        token = bearer

    # 3. Raise 401 if neither source yields a token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            detail="Could not validate credentials.",
        )

    # Verify the token is a valid, non-expired access token.
    user_id = decode_token(token, expected_type="access")

    # Confirm the user still exists in the database.
    # This handles the case where an account was deleted after
    # a token was issued — without this check, the deleted user
    # could still access the API until their token expires.
    user = await get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            detail="User account not found.",
        )

    # Return only the safe fields — never return password_hash.
    return {
        "id": user["id"],
        "email": user["email"],
        "created_at": user["created_at"],
    }
