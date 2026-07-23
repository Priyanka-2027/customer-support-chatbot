// components/UploadPanel.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Full upload UI — drop zone, file list, per-file status rows,
//   and the upload/reset action buttons.
//
//   Receives everything it needs from props (driven by useUpload).
//   Contains zero business logic — pure presentation.
// ─────────────────────────────────────────────────────────────

import { useRef, type DragEvent, type ChangeEvent } from "react";
import type { UploadFileState } from "../types";

interface UploadPanelProps {
  fileStates: UploadFileState[];
  isUploading: boolean;
  isDone: boolean;
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveFile: (id: string) => void;
  onUpload: () => void;
  onReset: () => void;
  onClose: () => void;
}

export default function UploadPanel({
  fileStates,
  isUploading,
  isDone,
  onAddFiles,
  onRemoveFile,
  onUpload,
  onReset,
  onClose,
}: UploadPanelProps) {

  // Ref to the hidden <input type="file"> element.
  // We trigger it programmatically when the drop zone is clicked
  // so we can style the drop zone freely without browser's default
  // file input appearance.
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Drag-and-drop handlers ─────────────────────────────────

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    // Prevent the browser's default behavior (open the file).
    // Without this, dropping a file on the page navigates away.
    e.preventDefault();
    // dataTransfer.dropEffect tells the browser what drag icon to show.
    // "copy" shows a + badge on the cursor.
    e.dataTransfer.dropEffect = "copy";
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    // e.dataTransfer.files is a FileList of dropped files.
    if (e.dataTransfer.files.length > 0) {
      onAddFiles(e.dataTransfer.files);
    }
  }

  // ── File input change handler ──────────────────────────────
  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    // e.target.files is null if the user cancelled the picker.
    if (e.target.files && e.target.files.length > 0) {
      onAddFiles(e.target.files);
      // Reset the input value so selecting the same file again
      // triggers onChange. Without this, a second pick of the
      // same file is silently ignored.
      e.target.value = "";
    }
  }

  // ── Derived state ──────────────────────────────────────────
  const pendingCount = fileStates.filter((f) => f.status === "pending").length;
  const successCount = fileStates.filter((f) => f.status === "success").length;
  const errorCount = fileStates.filter((f) => f.status === "error").length;
  const hasFiles = fileStates.length > 0;

  return (
    // Overlay — semi-transparent background that dims the chat behind it.
    // onClick on the overlay (not the panel) closes it.
    <div
      className="absolute inset-0 bg-black/40 flex items-center justify-center z-10 rounded-2xl"
      onClick={onClose}
    >
      {/* Panel card — stops click propagation so clicking inside
          the panel doesn't close it */}
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 flex flex-col max-h-[90%]"
        onClick={(e) => e.stopPropagation()}
      >

        {/* ── Header ──────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-sm font-semibold text-gray-800">
              Upload Documents
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              PDF files only · max 20MB each · up to 10 files
            </p>
          </div>
          {/* Close button */}
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded"
            aria-label="Close upload panel"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ── Scrollable body ──────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">

          {/* ── Drop zone — hidden when upload is done ──────── */}
          {!isDone && (
            <div
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-indigo-200 rounded-xl p-6 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/50 transition-colors"
              role="button"
              aria-label="Click or drag to add PDF files"
            >
              {/* Upload icon */}
              <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center mx-auto mb-3">
                <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-sm font-medium text-gray-700">
                Drop PDFs here or <span className="text-indigo-600">browse</span>
              </p>
              <p className="text-xs text-gray-400 mt-1">
                Selected: {fileStates.length} / 10
              </p>

              {/* Hidden file input — triggered by clicking the drop zone */}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                // multiple allows selecting more than one file at once
                // in the system file picker dialog.
                multiple
                className="hidden"
                onChange={handleInputChange}
                aria-hidden="true"
              />
            </div>
          )}

          {/* ── File list ─────────────────────────────────── */}
          {hasFiles && (
            <ul className="space-y-2" aria-label="Selected files">
              {fileStates.map((f) => (
                <FileRow
                  key={f.id}
                  fileState={f}
                  onRemove={() => onRemoveFile(f.id)}
                  // Can't remove files while uploading — prevents
                  // the file list from changing mid-request.
                  canRemove={!isUploading && !isDone}
                />
              ))}
            </ul>
          )}

          {/* ── Done summary ─────────────────────────────── */}
          {isDone && (
            <div className="rounded-xl bg-gray-50 border border-gray-200 p-4 text-sm space-y-1">
              <p className="font-semibold text-gray-700 mb-2">Upload complete</p>
              {successCount > 0 && (
                <p className="text-green-700">
                  ✅ {successCount} file{successCount !== 1 ? "s" : ""} added to knowledge base
                </p>
              )}
              {errorCount > 0 && (
                <p className="text-red-600">
                  ❌ {errorCount} file{errorCount !== 1 ? "s" : ""} failed
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Footer actions ──────────────────────────────── */}
        <div className="px-5 py-4 border-t border-gray-100 flex gap-2 justify-end">
          {!isDone ? (
            <>
              {/* Cancel / clear selection */}
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors rounded-lg hover:bg-gray-100"
              >
                Cancel
              </button>

              {/* Upload button — disabled when no pending files or uploading */}
              <button
                onClick={onUpload}
                disabled={pendingCount === 0 || isUploading}
                className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {isUploading ? (
                  <>
                    {/* Spinner during upload */}
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    Processing…
                  </>
                ) : (
                  `Upload ${pendingCount > 0 ? pendingCount : ""} PDF${pendingCount !== 1 ? "s" : ""}`
                )}
              </button>
            </>
          ) : (
            <>
              {/* Upload more — resets the panel state */}
              <button
                onClick={onReset}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors rounded-lg hover:bg-gray-100"
              >
                Upload more
              </button>
              {/* Done — closes the panel */}
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Done
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// FileRow — private sub-component for a single file entry
// ─────────────────────────────────────────────────────────────
// Kept in this file because it's only used by UploadPanel.
// Extracted into its own function for readability.

interface FileRowProps {
  fileState: UploadFileState;
  onRemove: () => void;
  canRemove: boolean;
}

function FileRow({ fileState, onRemove, canRemove }: FileRowProps) {
  const { file, status, chunks_created, error } = fileState;

  // Format file size: bytes → "1.2 MB" or "340 KB"
  const sizeLabel =
    file.size >= 1_048_576
      ? `${(file.size / 1_048_576).toFixed(1)} MB`
      : `${Math.round(file.size / 1024)} KB`;

  return (
    <li className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 border border-gray-100">

      {/* Status icon */}
      <div className="flex-shrink-0 mt-0.5">
        {status === "pending" && (
          // Hollow circle = waiting
          <div className="w-5 h-5 rounded-full border-2 border-gray-300" aria-label="Pending" />
        )}
        {status === "uploading" && (
          // Spinning indigo circle = in progress
          <svg className="w-5 h-5 text-indigo-500 animate-spin" fill="none" viewBox="0 0 24 24" aria-label="Uploading">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        )}
        {status === "success" && (
          // Green checkmark = done
          <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-label="Success">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        )}
        {status === "error" && (
          // Red X = failed
          <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-label="Error">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        )}
      </div>

      {/* File info */}
      <div className="flex-1 min-w-0">
        {/* Filename — truncate long names with ellipsis */}
        <p className="text-sm font-medium text-gray-800 truncate">{file.name}</p>

        {/* Secondary info line */}
        <p className="text-xs text-gray-400 mt-0.5">
          {status === "success" && chunks_created !== undefined
            ? `✓ ${chunks_created} chunks added · ${sizeLabel}`
            : status === "error" && error
            ? error
            : sizeLabel}
        </p>
      </div>

      {/* Remove button — only shown when canRemove is true */}
      {canRemove && (
        <button
          onClick={onRemove}
          className="flex-shrink-0 text-gray-300 hover:text-red-400 transition-colors p-0.5"
          aria-label={`Remove ${file.name}`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </li>
  );
}
