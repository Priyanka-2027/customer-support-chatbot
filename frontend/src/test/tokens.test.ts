/**
 * tokens.test.ts — no-op stub contract tests
 *
 * tokens.ts is now a no-op stub. Token storage has migrated to
 * HttpOnly cookies managed by the server. These tests document
 * the stub's contract: all functions are safe to call and return
 * the expected null values without touching localStorage.
 *
 * Validates: Requirement 7 (Frontend Removal of localStorage Token Management)
 */

import { saveTokens, loadTokens, clearTokens, getAccessToken, getRefreshToken } from "../api/tokens";

describe("tokens (no-op stub)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  // ── Read functions always return null ──────────────────────

  it("loadTokens always returns null (no localStorage reads)", () => {
    expect(loadTokens()).toBeNull();
  });

  it("getAccessToken always returns null (token is in HttpOnly cookie)", () => {
    expect(getAccessToken()).toBeNull();
  });

  it("getRefreshToken always returns null (token is in HttpOnly cookie)", () => {
    expect(getRefreshToken()).toBeNull();
  });

  // ── Write functions are no-ops ─────────────────────────────

  it("saveTokens does not write to localStorage", () => {
    saveTokens({ accessToken: "acc123", refreshToken: "ref456" });
    expect(localStorage.length).toBe(0);
  });

  it("saveTokens does not cause loadTokens to return non-null", () => {
    saveTokens({ accessToken: "acc123", refreshToken: "ref456" });
    expect(loadTokens()).toBeNull();
  });

  it("saveTokens does not cause getAccessToken to return a value", () => {
    saveTokens({ accessToken: "acc-test", refreshToken: "ref-test" });
    expect(getAccessToken()).toBeNull();
  });

  it("saveTokens does not cause getRefreshToken to return a value", () => {
    saveTokens({ accessToken: "acc-test", refreshToken: "ref-test" });
    expect(getRefreshToken()).toBeNull();
  });

  it("clearTokens is a no-op — does not throw", () => {
    expect(() => clearTokens()).not.toThrow();
  });

  it("clearTokens does not affect localStorage", () => {
    // Pre-populate localStorage manually to verify clearTokens doesn't touch it
    localStorage.setItem("some_key", "some_value");
    clearTokens();
    expect(localStorage.getItem("some_key")).toBe("some_value");
  });
});
