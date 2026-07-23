// api/chat.ts
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   HTTP calls for chat and document upload.
//
//   Uses the shared apiClient from api/auth.ts which has:
//     - Automatic Authorization header injection
//     - Silent token refresh on 401
//   So these functions need zero auth-specific code.
// ─────────────────────────────────────────────────────────────

import axios from "axios";
import type { BatchUploadResponse, ChatApiResponse } from "../types";
import { apiClient } from "./auth";

/**
 * Send a question to the backend and return the AI response.
 * The Authorization header is attached automatically by the
 * request interceptor in api/auth.ts.
 *
 * @param question         - The user's question string.
 * @param conversation_id  - Optional: continue an existing conversation.
 * @returns ChatApiResponse with answer, sources, and conversation_id.
 */
export async function sendMessage(
  question: string,
  conversation_id?: string
): Promise<ChatApiResponse> {
  try {
    const response = await apiClient.post<ChatApiResponse>("/api/v1/chat", {
      question,
      // Only include conversation_id if provided — omitting it
      // causes the backend to auto-create a new conversation.
      ...(conversation_id ? { conversation_id } : {}),
    });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.response) {
        const detail = error.response.data?.detail;
        const message = typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ")
            : `Server error (${error.response.status}). Please try again.`;
        throw new Error(message);
      } else if (error.request) {
        throw new Error(
          "Cannot reach the server. Make sure the backend is running."
        );
      }
    }
    throw new Error("Something went wrong. Please try again.");
  }
}

/**
 * Upload multiple PDF documents to the knowledge base.
 * Authorization header is attached automatically.
 */
export async function uploadDocuments(
  files: File[]
): Promise<BatchUploadResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  try {
    const response = await apiClient.post<BatchUploadResponse>(
      "/api/v1/upload/batch",
      formData,
      {
        // Let the browser set Content-Type with the correct multipart boundary.
        // The default apiClient header sets application/json which breaks FormData.
        headers: { "Content-Type": undefined },
      }
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.response) {
        const detail = error.response.data?.detail;
        const message = typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ")
            : `Upload failed (${error.response.status}). Please try again.`;
        throw new Error(message);
      } else if (error.request) {
        throw new Error(
          "Cannot reach the server. Make sure the backend is running."
        );
      }
    }
    throw new Error("Upload failed. Please try again.");
  }
}
