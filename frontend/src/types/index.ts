// types/index.ts
// ─────────────────────────────────────────────────────────────
// Shared TypeScript types used across components and API layer.
// ─────────────────────────────────────────────────────────────

/** A single source chunk reference returned by the backend. */
export interface SourceDocument {
  filename: string;
  page: number;
  chunk_text: string;
  chunk_index: number;
}

/** The shape of a successful POST /chat response from the API. */
export interface ChatApiResponse {
  answer: string;
  sources: SourceDocument[];
  conversation_id?: string;
}

/** A single message in the conversation. */
export interface Message {
  id: string;
  role: "user" | "bot";
  text: string;
  sources?: SourceDocument[];
  timestamp: Date;
}

// ── Upload types ──────────────────────────────────────────────

export interface FileUploadResult {
  filename: string;
  success: boolean;
  chunks_created: number;
  error: string | null;
}

export interface BatchUploadResponse {
  total_files: number;
  successful: number;
  failed: number;
  total_chunks_created: number;
  results: FileUploadResult[];
}

export type UploadStatus = "pending" | "uploading" | "success" | "error";

export interface UploadFileState {
  id: string;
  file: File;
  status: UploadStatus;
  chunks_created?: number;
  error?: string;
}

// ── Auth types ────────────────────────────────────────────────

/** Authenticated user profile returned by GET /auth/me */
export interface User {
  id: string;
  email: string;
  created_at: string;
}

/** Response from POST /auth/login and POST /auth/refresh */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/** What we store in localStorage */
export interface StoredTokens {
  accessToken: string;
  refreshToken: string;
}
