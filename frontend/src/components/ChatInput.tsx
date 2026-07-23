// components/ChatInput.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Render the text input and send button at the bottom of the chat.
//   Manage the local input value state.
//   Submit on Enter key or Send button click.
//   Disable itself while a request is in flight (isLoading).
// ─────────────────────────────────────────────────────────────

import { useState, type KeyboardEvent, type FormEvent } from "react";

interface ChatInputProps {
  /** Called with the trimmed question string when the user submits */
  onSend: (question: string) => void;
  /** When true, the input and button are disabled */
  isLoading: boolean;
}

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  // Local state for the current input value.
  // This lives here, not in App, because no other component
  // needs to know what the user is currently typing.
  const [value, setValue] = useState("");

  // Shared submit handler — used by both the form's onSubmit
  // and the keyboard Enter handler below.
  function handleSubmit(e?: FormEvent) {
    // Prevent the browser from reloading the page on form submit.
    e?.preventDefault();

    const trimmed = value.trim();

    // Don't submit if empty or already waiting for a response.
    if (!trimmed || isLoading) return;

    // Call the parent's handler with the question text.
    onSend(trimmed);

    // Clear the input immediately after submitting.
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Submit on Enter key press — but NOT on Shift+Enter.
    // Shift+Enter inserts a newline, which is standard behavior
    // for multi-line chat inputs.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();    // prevent newline being added to textarea
      handleSubmit();
    }
  }

  return (
    // form wrapper enables the browser's native submit behavior
    // (Enter key, form validation) without extra event listeners.
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 p-4 border-t border-gray-200 bg-white"
    >
      {/* ── Textarea ───────────────────────────────────────── */}
      {/* Using textarea instead of <input> so the box can grow
          for multi-line messages via the resize-none + rows approach.
          rows={1} starts single-line but allows the user to type more. */}
      <textarea
        // value + onChange = controlled component.
        // React owns the value; the textarea displays what React says.
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}

        // disabled while waiting prevents double-submits and gives
        // clear visual feedback that the system is busy.
        disabled={isLoading}

        placeholder="Type your question..."
        rows={1}
        // max-h-32 caps the textarea at ~5 lines before scrolling.
        // resize-none prevents the user from manually resizing.
        className="flex-1 resize-none max-h-32 rounded-xl border border-gray-300 px-4 py-2.5 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
        // maxLength matches the backend's ChatRequest max_length validation.
        // This prevents the user from typing more than the API accepts.
        maxLength={1000}

        aria-label="Type your question"
      />

      {/* ── Send button ────────────────────────────────────── */}
      <button
        type="submit"
        disabled={isLoading || !value.trim()}
        className="flex-shrink-0 w-10 h-10 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        aria-label="Send message"
      >
        {isLoading ? (
          // Spinning circle while loading — simple CSS animation,
          // no library needed.
          <svg
            className="w-4 h-4 text-white animate-spin"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12" cy="12" r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v8H4z"
            />
          </svg>
        ) : (
          // Paper plane send icon when idle
          <svg
            className="w-4 h-4 text-white"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
            />
          </svg>
        )}
      </button>
    </form>
  );
}
