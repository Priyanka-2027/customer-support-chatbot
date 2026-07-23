// hooks/useUpload.ts
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Manage the full lifecycle of a batch file upload:
//     - Track selected files with per-file status
//     - Validate files before sending
//     - Call the API and update per-file status from results
//     - Expose clear/reset so the UI can start fresh
//
// Mirrors useChat's pattern: all logic in the hook,
// the component stays purely presentational.
// ─────────────────────────────────────────────────────────────

import { useState, useCallback } from "react";
import type { UploadFileState } from "../types";
import { uploadDocuments } from "../api/chat";

// ── Constants ──────────────────────────────────────────────────
const MAX_FILE_SIZE_MB = 20;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
const MAX_FILES = 10;

// ── Return type ────────────────────────────────────────────────
interface UseUploadReturn {
  /** Files currently in the queue with their per-file status */
  fileStates: UploadFileState[];
  /** True while the upload request is in flight */
  isUploading: boolean;
  /** True when at least one file has been processed (success or fail) */
  isDone: boolean;
  /** Add files from the file picker to the queue */
  addFiles: (files: FileList | File[]) => void;
  /** Remove a single file from the queue by its id */
  removeFile: (id: string) => void;
  /** Upload all pending files */
  uploadAll: () => Promise<void>;
  /** Reset everything to initial state */
  reset: () => void;
}

// ── ID generator ──────────────────────────────────────────────
function generateId(): string {
  return crypto.randomUUID();
}

// ─────────────────────────────────────────────────────────────
export function useUpload(): UseUploadReturn {

  // fileStates: one entry per file the user has selected.
  // Each entry tracks that file's individual lifecycle: pending →
  // uploading → success | error.
  const [fileStates, setFileStates] = useState<UploadFileState[]>([]);

  // isUploading: true while the POST /upload/batch request is in flight.
  // Disables the upload button and file picker to prevent double-submits.
  const [isUploading, setIsUploading] = useState(false);

  // isDone: true once the batch has been processed at least once.
  // Used to show the results summary panel instead of the upload form.
  const [isDone, setIsDone] = useState(false);


  // ── addFiles ────────────────────────────────────────────────
  // Called when the user selects files via the file picker or
  // drops them onto the drop zone.
  //
  // Validates each file client-side before adding it to the queue.
  // Client-side validation is UX, not security — the backend
  // validates again. But catching obvious errors here avoids a
  // round-trip just to get a validation error back.
  const addFiles = useCallback((incoming: FileList | File[]) => {
    // Convert FileList (browser DOM type) to plain Array.
    // FileList is array-like but not a true array — it lacks .map(), .filter() etc.
    const fileArray = Array.from(incoming);

    setFileStates((prev) => {
      // How many files are already in the queue (not counting errors
      // that the user may want to retry by removing and re-adding).
      const currentCount = prev.filter((f) => f.status !== "error").length;

      // Validate and build state entries for each new file.
      const newEntries: UploadFileState[] = [];

      for (const file of fileArray) {
        // ── Duplicate check ──────────────────────────────────
        // If a file with the same name is already in the queue,
        // skip it. Comparing by name is a heuristic — same name
        // doesn't guarantee same content, but it prevents the most
        // common accidental duplicate (re-selecting the same file).
        const isDuplicate = prev.some((f) => f.file.name === file.name);
        if (isDuplicate) continue;

        // ── File count limit ─────────────────────────────────
        if (currentCount + newEntries.length >= MAX_FILES) {
          // Silently stop adding once the limit is reached.
          // The UI shows the current count so the user knows why.
          break;
        }

        // ── Type validation ──────────────────────────────────
        // file.type is set by the browser based on the file extension.
        // We check both the MIME type and the extension for robustness.
        const isPdf =
          file.type === "application/pdf" ||
          file.name.toLowerCase().endsWith(".pdf");

        if (!isPdf) {
          // Add the file as an error state so the user can see
          // what was rejected and why, rather than silent rejection.
          newEntries.push({
            id: generateId(),
            file,
            status: "error",
            error: "Not a PDF file.",
          });
          continue;
        }

        // ── Size validation ───────────────────────────────────
        if (file.size > MAX_FILE_SIZE_BYTES) {
          newEntries.push({
            id: generateId(),
            file,
            status: "error",
            error: `File too large (max ${MAX_FILE_SIZE_MB}MB).`,
          });
          continue;
        }

        // ── Valid file — add as pending ───────────────────────
        newEntries.push({
          id: generateId(),
          file,
          status: "pending",
        });
      }

      return [...prev, ...newEntries];
    });
  }, []);


  // ── removeFile ──────────────────────────────────────────────
  // Remove one file from the queue by its generated id.
  // Used by the × button on each file row.
  const removeFile = useCallback((id: string) => {
    setFileStates((prev) => prev.filter((f) => f.id !== id));
  }, []);


  // ── uploadAll ───────────────────────────────────────────────
  // Upload all files currently in "pending" status.
  // Files already in "success" or "error" are skipped.
  const uploadAll = useCallback(async () => {
    // Collect only the files that haven't been processed yet.
    const pendingFiles = fileStates
      .filter((f) => f.status === "pending")
      .map((f) => f.file);

    if (pendingFiles.length === 0) return;
    if (isUploading) return;  // prevent double-submit

    setIsUploading(true);

    // ── Mark all pending files as "uploading" ────────────────
    // This gives immediate visual feedback — each file row shows
    // a spinner before the server has even received the request.
    setFileStates((prev) =>
      prev.map((f) =>
        f.status === "pending" ? { ...f, status: "uploading" } : f
      )
    );

    try {
      // ── Send all files in one batch request ──────────────────
      // uploadDocuments() sends POST /api/v1/upload/batch.
      // Returns per-file results including success/fail and chunk count.
      const batchResult = await uploadDocuments(pendingFiles);

      // ── Map server results back to our file states ─────────
      // batchResult.results is ordered the same way as pendingFiles
      // (same order the files were appended to FormData).
      // We match them by index to update each file's status.
      setFileStates((prev) => {
        // Build a name → result map for O(1) lookup.
        // The server returns results keyed by filename.
        const resultMap = new Map(
          batchResult.results.map((r) => [r.filename, r])
        );

        return prev.map((f) => {
          // Only update files that were in the "uploading" state.
          // Files that were already "success" or "error" stay as-is.
          if (f.status !== "uploading") return f;

          // Look up the server result for this file by name.
          const serverResult = resultMap.get(f.file.name);

          if (!serverResult) {
            // No matching result from server — treat as error.
            return { ...f, status: "error", error: "No result from server." };
          }

          if (serverResult.success) {
            return {
              ...f,
              status: "success",
              // chunks_created tells the user how much knowledge was added.
              chunks_created: serverResult.chunks_created,
            };
          } else {
            return {
              ...f,
              status: "error",
              // Safely serialize error — backend may return string or object
              error: typeof serverResult.error === "string"
                ? serverResult.error
                : serverResult.error
                  ? JSON.stringify(serverResult.error)
                  : "Processing failed.",
            };
          }
        });
      });

      setIsDone(true);

    } catch (err) {
      // ── Network-level failure ─────────────────────────────
      // The whole request failed (server down, network error).
      // Mark ALL uploading files as failed with the error message.
      const errorText =
        err instanceof Error ? err.message : "Upload failed. Please retry.";

      setFileStates((prev) =>
        prev.map((f) =>
          f.status === "uploading"
            ? { ...f, status: "error", error: errorText }
            : f
        )
      );

      setIsDone(true);

    } finally {
      // Always clear uploading state — same pattern as useChat.
      setIsUploading(false);
    }
  }, [fileStates, isUploading]);


  // ── reset ───────────────────────────────────────────────────
  // Clear everything and return to the initial state.
  // Called by the "Upload more" button after a completed batch.
  const reset = useCallback(() => {
    setFileStates([]);
    setIsUploading(false);
    setIsDone(false);
  }, []);


  return {
    fileStates,
    isUploading,
    isDone,
    addFiles,
    removeFile,
    uploadAll,
    reset,
  };
}
