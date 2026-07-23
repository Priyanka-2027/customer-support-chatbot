/**
 * useAuth.test.tsx — auth hook tests (cookie-based session)
 * Validates: Requirements 8.1–8.7 (HttpOnly cookie auth)
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { useAuth } from "../hooks/useAuth";

// Mock API module — cookie management is handled by the browser/server,
// not by this hook directly.
vi.mock("../api/auth", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logoutApi: vi.fn(),
}));

import { getMe, login as apiLogin, register as apiRegister, logoutApi } from "../api/auth";

describe("useAuth", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // ── Session restore ────────────────────────────────────────

  it("initialises with isInitialised=false then true (Req 8.1)", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: "u1", email: "a@b.com", created_at: "2024-01-01" });

    const { result } = renderHook(() => useAuth());
    expect(result.current.isInitialised).toBe(false);

    await waitFor(() => expect(result.current.isInitialised).toBe(true));
    expect(result.current.user?.email).toBe("a@b.com");
  });

  it("calls getMe on startup to probe session cookie (Req 8.1)", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: "u1", email: "a@b.com", created_at: "2024-01-01" });

    renderHook(() => useAuth());
    await waitFor(() => expect(vi.mocked(getMe)).toHaveBeenCalledTimes(1));
  });

  it("sets user=null and isInitialised=true when getMe returns 401 (Req 8.2, 8.3)", async () => {
    vi.mocked(getMe).mockRejectedValue(new Error("401 Unauthorized"));

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isInitialised).toBe(true));

    expect(result.current.user).toBeNull();
  });

  // ── Login ──────────────────────────────────────────────────

  it("login calls apiLogin and sets user from returned profile (Req 8.5)", async () => {
    // Startup: no valid cookie
    vi.mocked(getMe).mockRejectedValueOnce(new Error("401"));
    // Login: apiLogin now returns User directly (cookie-based flow)
    vi.mocked(apiLogin).mockResolvedValue({ id: "u2", email: "b@b.com", created_at: "2024-01-01" });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isInitialised).toBe(true));

    await act(async () => {
      await result.current.login("b@b.com", "password");
    });

    expect(apiLogin).toHaveBeenCalledWith("b@b.com", "password");
    expect(result.current.user?.email).toBe("b@b.com");
  });

  it("login sets error state on failure (Req 8.5)", async () => {
    vi.mocked(getMe).mockRejectedValueOnce(new Error("401"));
    vi.mocked(apiLogin).mockRejectedValue(new Error("Invalid email or password."));

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isInitialised).toBe(true));

    await act(async () => {
      await result.current.login("x@x.com", "wrong").catch(() => {});
    });

    expect(result.current.error).toBe("Invalid email or password.");
    expect(result.current.user).toBeNull();
  });

  // ── Register ───────────────────────────────────────────────

  it("register calls apiRegister and sets user from returned profile (Req 8.4)", async () => {
    vi.mocked(getMe).mockRejectedValueOnce(new Error("401"));
    vi.mocked(apiRegister).mockResolvedValue({ id: "u3", email: "c@c.com", created_at: "2024-01-01" });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isInitialised).toBe(true));

    await act(async () => {
      await result.current.register("c@c.com", "password123");
    });

    expect(apiRegister).toHaveBeenCalledWith("c@c.com", "password123");
    expect(result.current.user?.email).toBe("c@c.com");
  });

  // ── Logout ─────────────────────────────────────────────────

  it("logout calls logoutApi and sets user=null (Req 8.6)", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: "u1", email: "a@b.com", created_at: "2024-01-01" });
    vi.mocked(logoutApi).mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => {
      await result.current.logout();
    });

    expect(logoutApi).toHaveBeenCalledTimes(1);
    expect(result.current.user).toBeNull();
  });

  it("logout clears user even if logoutApi fails (Req 8.6)", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: "u1", email: "a@b.com", created_at: "2024-01-01" });
    vi.mocked(logoutApi).mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => {
      await result.current.logout();
    });

    // User must be null even though the server call failed
    expect(result.current.user).toBeNull();
  });

  it("logout is async and clears error state (Req 8.6)", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: "u1", email: "a@b.com", created_at: "2024-01-01" });
    vi.mocked(logoutApi).mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.error).toBeNull();
  });
});
