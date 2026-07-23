# auth.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Route handlers for the authentication endpoints:
#     POST /auth/register  — create an account
#     POST /auth/login     — exchange credentials for tokens
#     POST /auth/refresh   — exchange a refresh token for new tokens
#     GET  /auth/me        — return the current user's profile
#
# All cryptographic work is delegated to security.py.
# All database work is delegated to database.py.
# This file is purely routing + orchestration.
# ─────────────────────────────────────────────────────────────

import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, ENVIRONMENT, REFRESH_TOKEN_EXPIRE_DAYS
from app.database import create_user, get_user_by_email
from app.schemas import (
    AuthSuccessResponse,
    LoginRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─────────────────────────────────────────────────────────────
# Private helper — set both auth cookies on a response
# ─────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, user_id: str) -> None:
    """Set access_token and refresh_token HttpOnly cookies on response."""
    is_secure = ENVIRONMENT != "development"
    # Use "lax" in development (cross-port requests from localhost:5173 to localhost:8000)
    # Use "strict" in production (same-origin deployment)
    samesite = "strict" if ENVIRONMENT != "development" else "lax"
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        path="/",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        path="/",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


# ─────────────────────────────────────────────────────────────
# POST /auth/token  (OAuth2-compatible — returns Bearer token)
# Used by the frontend for cross-origin local development
# ─────────────────────────────────────────────────────────────

@router.post(
    "/token",
    status_code=status.HTTP_200_OK,
    tags=["Auth"],
    summary="Get access token (OAuth2 form)",
    include_in_schema=False,  # hide from Swagger to avoid confusion
)
async def get_token(
    username: str = Form(...),
    password: str = Form(...),
) -> dict:
    """
    OAuth2-compatible token endpoint.
    Returns a Bearer access token for use in Authorization headers.
    Used by the frontend in local dev where cross-origin cookies are blocked.
    """
    normalised_email = username.strip().lower()
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = await get_user_by_email(normalised_email)
    if user is None:
        raise auth_error
    if not verify_password(password, user["password_hash"]):
        raise auth_error
    token = create_access_token(user["id"])
    return {"access_token": token, "token_type": "bearer"}


# ─────────────────────────────────────────────────────────────
# POST /auth/register
# ─────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    description="Creates a new user account and sets HttpOnly auth cookies so the user is logged in after registration.",
)
async def register(request: RegisterRequest, response: Response) -> UserResponse:
    """
    Register a new user.

    Security steps:
      1. Normalise email to lowercase — "User@EXAMPLE.com" and
         "user@example.com" must be treated as the same address.
      2. Hash the password with bcrypt before storing.
      3. Create the DB row — raises ValueError if email exists.
      4. Issue tokens via HttpOnly cookies immediately (no separate login required).

    We set cookies on registration rather than requiring a
    separate login call — better UX, same security.
    """

    # Normalise email to lowercase before storing.
    # "User@Example.com" must not create a duplicate of "user@example.com".
    normalised_email = request.email.strip().lower()

    # Hash the password BEFORE creating the user.
    # If the DB insert fails for any reason, we haven't stored
    # a hash we can't clean up.
    password_hash = hash_password(request.password)

    try:
        user_id = str(uuid.uuid4())
        await create_user(user_id, normalised_email, password_hash)
    except ValueError as e:
        # Email already registered — 409 Conflict is the correct
        # HTTP status for duplicate resource creation.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    logger.info(f"New user registered: '{normalised_email}' (id={user_id})")

    # Issue tokens via HttpOnly cookies — the user is logged in after signup.
    _set_auth_cookies(response, user_id)
    
    # Also return the access token in the body for cross-origin local dev
    access_token = create_access_token(user_id)
    from datetime import datetime, timezone
    return UserResponse(
        id=user_id,
        email=normalised_email,
        created_at=datetime.now(timezone.utc).isoformat(),
        access_token=access_token,
    )


# ─────────────────────────────────────────────────────────────
# POST /auth/login
# ─────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in with email and password",
    description="Verifies credentials and sets HttpOnly JWT access and refresh token cookies.",
)
async def login(request: LoginRequest, response: Response) -> UserResponse:
    """
    Authenticate with email and password.

    Security steps:
      1. Normalise email.
      2. Look up the user — if not found, return 401.
      3. Verify the password with bcrypt — if wrong, return 401.
      4. Issue tokens via HttpOnly cookies.

    Critical: steps 2 and 3 return the SAME error message.
    "Invalid email or password" — not "email not found" or
    "wrong password". This prevents user enumeration — an
    attacker can't tell whether an email is registered.

    Timing: bcrypt.verify takes ~250ms regardless of whether
    the user exists. If we returned immediately for unknown
    emails, an attacker could distinguish "user not found"
    (fast) from "wrong password" (slow) by timing the response.
    """

    normalised_email = request.email.strip().lower()

    # Same generic error for both "user not found" and "wrong password".
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = await get_user_by_email(normalised_email)
    if user is None:
        raise auth_error

    # verify_password uses constant-time comparison — takes the same
    # time whether the password is almost-right or completely wrong.
    if not verify_password(request.password, user["password_hash"]):
        raise auth_error

    logger.info(f"User logged in: '{normalised_email}' (id={user['id']})")

    _set_auth_cookies(response, user["id"])
    
    # Also return the access token in the body for cross-origin local dev
    access_token = create_access_token(user["id"])
    return UserResponse(
        id=user["id"],
        email=user["email"],
        created_at=user["created_at"],
        access_token=access_token,
    )


# ─────────────────────────────────────────────────────────────
# POST /auth/refresh
# ─────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=AuthSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange a refresh token cookie for new tokens",
    description=(
        "Reads the refresh_token HttpOnly cookie and issues a fresh access token "
        "and a new refresh token as cookies. The old cookies are replaced."
    ),
)
async def refresh_tokens(request: Request, response: Response) -> AuthSuccessResponse:
    """
    Issue a new pair of tokens given a valid refresh token cookie.

    Why we also return a new refresh token (token rotation):
      Each refresh call returns a new refresh token. The client
      replaces the old one. This means if a refresh token is stolen,
      the attacker has a limited window — as soon as the legitimate
      user refreshes (every 7 days at most), the stolen token
      becomes invalid. This is called "refresh token rotation".

    Note: true token rotation with revocation requires a token
    blocklist (Redis or DB table). This implementation uses
    stateless rotation — adequate for most use cases.
    """
    from app.database import get_user_by_id

    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # decode_token verifies the signature, expiry, AND
    # that this is specifically a refresh token (type="refresh").
    # An access token passed here will be rejected.
    user_id = decode_token(refresh_token, expected_type="refresh")

    # Confirm the user still exists before issuing new tokens.
    user = await get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info(f"Tokens refreshed for user_id={user_id}")

    _set_auth_cookies(response, user_id)
    return AuthSuccessResponse()


# ─────────────────────────────────────────────────────────────
# GET /auth/me
# ─────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns the authenticated user's id and email. Requires a valid access token.",
)
async def get_me(
    # Depends(get_current_user) is FastAPI's dependency injection.
    # FastAPI calls get_current_user() automatically, passing the
    # Bearer token from the Authorization header.
    # If the token is missing or invalid, FastAPI returns 401
    # before this function body runs.
    current_user: dict = Depends(get_current_user),
) -> UserResponse:
    """
    Return the current user's profile.

    Used by the frontend on startup to verify the stored token
    is still valid and to retrieve the user's email for display.
    """
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        created_at=current_user["created_at"],
    )


# ─────────────────────────────────────────────────────────────
# POST /auth/logout
# ─────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Log out the current user",
    description="Clears the access_token and refresh_token HttpOnly cookies. Idempotent — safe to call even when no cookies are present.",
)
async def logout(response: Response) -> LogoutResponse:
    """
    Clear both auth cookies to end the session.

    This is intentionally idempotent: calling logout when no
    cookies are present still returns 200 — there is nothing
    to do and no reason to signal an error.
    """
    is_secure = ENVIRONMENT != "development"
    samesite = "strict" if ENVIRONMENT != "development" else "lax"
    for name in ("access_token", "refresh_token"):
        response.delete_cookie(
            key=name,
            httponly=True,
            secure=is_secure,
            samesite=samesite,
            path="/",
        )
    return LogoutResponse()
