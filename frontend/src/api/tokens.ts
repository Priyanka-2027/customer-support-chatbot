// api/tokens.ts
// ─────────────────────────────────────────────────────────────
// No-op stub — token storage has moved to HttpOnly cookies.
// These functions are retained with identical signatures to
// prevent import errors in code that has not yet been updated.
// ─────────────────────────────────────────────────────────────

import type { StoredTokens } from "../types";

/** No-op: tokens are now stored in HttpOnly cookies by the server. */
export function saveTokens(_tokens: StoredTokens): void {}

/** No-op: returns null — session state is probed via getMe(). */
export function loadTokens(): StoredTokens | null { return null; }

/** No-op: returns null — access token is in an HttpOnly cookie. */
export function getAccessToken(): string | null { return null; }

/** No-op: returns null — refresh token is in an HttpOnly cookie. */
export function getRefreshToken(): string | null { return null; }

/** No-op: cookies are cleared by the server's logout endpoint. */
export function clearTokens(): void {}
