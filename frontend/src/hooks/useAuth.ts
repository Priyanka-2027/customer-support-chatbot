// hooks/useAuth.ts
import { useState, useEffect, useCallback } from "react";
import type { User } from "../types";
import {
  getMe,
  login as apiLogin,
  logoutApi,
  register as apiRegister,
  setAccessToken,
} from "../api/auth";

interface UseAuthReturn {
  user: User | null;
  isLoading: boolean;
  error: string | null;
  isInitialised: boolean;
  register: (email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export function useAuth(): UseAuthReturn {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isInitialised, setIsInitialised] = useState(false);

  // ── Startup: try cookie-based session restore ─────────────
  useEffect(() => {
    async function restoreSession() {
      try {
        const profile = await getMe();
        setUser(profile);
      } catch {
        setUser(null);
      } finally {
        setIsInitialised(true);
      }
    }
    restoreSession();
  }, []);

  // ── register ───────────────────────────────────────────────
  const register = useCallback(async (email: string, password: string) => {
    setError(null);
    setIsLoading(true);
    try {
      // apiRegister returns User and stores the Bearer token in memory
      const profile = await apiRegister(email, password);
      setUser(profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ── login ──────────────────────────────────────────────────
  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    setIsLoading(true);
    try {
      // apiLogin returns User and stores the Bearer token in memory
      const profile = await apiLogin(email, password);
      setUser(profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ── logout ─────────────────────────────────────────────────
  const logout = useCallback(async () => {
    try {
      await logoutApi(); // also clears the in-memory token
    } catch {
      // ignore server errors — still clear local state
      setAccessToken(null);
    } finally {
      setUser(null);
      setError(null);
    }
  }, []);

  return { user, isLoading, error, isInitialised, register, login, logout };
}
