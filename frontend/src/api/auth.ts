// api/auth.ts
import axios from "axios";
import type { User } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

// ── In-memory token store (safe from XSS — not in localStorage) ──
let _accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

// ── Shared axios instance ──────────────────────────────────────
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 90000, // 90 seconds — handles Render free tier cold starts (~50s)
  withCredentials: true,
});

// Attach Bearer token to every request if one is in memory
apiClient.interceptors.request.use((config) => {
  const token = _accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function extractError(error: unknown, fallback: string): never {
  if (axios.isAxiosError(error) && error.response?.data?.detail) {
    throw new Error(error.response.data.detail);
  }
  throw new Error(fallback);
}

// Backend returns User + optional access_token field
interface AuthResponse extends User {
  access_token?: string;
}

/**
 * Register — returns user data and stores access token in memory.
 */
export async function register(email: string, password: string): Promise<User> {
  try {
    const response = await apiClient.post<AuthResponse>("/api/v1/auth/register", { email, password });
    // Store the token immediately so subsequent requests use Bearer auth
    if (response.data.access_token) {
      setAccessToken(response.data.access_token);
    }
    const { access_token: _token, ...user } = response.data;
    return user as User;
  } catch (error) {
    extractError(error, "Registration failed. Please try again.");
  }
}

/**
 * Login — returns user data and stores access token in memory.
 */
export async function login(email: string, password: string): Promise<User> {
  try {
    const response = await apiClient.post<AuthResponse>("/api/v1/auth/login", { email, password });
    // Store the token immediately so subsequent requests use Bearer auth
    if (response.data.access_token) {
      setAccessToken(response.data.access_token);
    }
    const { access_token: _token, ...user } = response.data;
    return user as User;
  } catch (error) {
    extractError(error, "Login failed. Please try again.");
  }
}

/**
 * Fetch the current user's profile (uses cookie or Bearer token).
 */
export async function getMe(): Promise<User> {
  try {
    const response = await apiClient.get<User>("/api/v1/auth/me");
    return response.data;
  } catch (error) {
    extractError(error, "Could not load user profile.");
  }
}

/**
 * Log out — clears in-memory token and instructs backend to clear cookies.
 */
export async function logoutApi(): Promise<void> {
  setAccessToken(null);
  await apiClient.post("/api/v1/auth/logout");
}
