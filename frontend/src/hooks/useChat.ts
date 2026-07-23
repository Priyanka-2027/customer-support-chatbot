// hooks/useChat.ts
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Extract ALL connection logic — API calls, state management,
//   loading state, error handling — into one reusable hook.
//
// Why a custom hook?
//   App.tsx currently mixes UI layout with data-fetching logic.
//   A custom hook separates concerns cleanly:
//     - App.tsx  → layout and composition only
//     - useChat  → state + API + error handling
//
//   This also makes the logic unit-testable without rendering
//   any UI at all (React Testing Library + renderHook).
// ─────────────────────────────────────────────────────────────

import { useState, useCallback } from "react";
import type { Message } from "../types";
import { sendMessage } from "../api/chat";

// ── Return type of the hook ────────────────────────────────────
// Explicitly typing what the hook returns makes it self-documenting
// and catches misuse at compile time.
interface UseChatReturn {
  /** Full conversation history, ordered oldest → newest */
  messages: Message[];

  /** True while the API request is in flight */
  isLoading: boolean;

  /**
   * Most recent error message, or null if the last request succeeded.
   * Cleared automatically when the next request starts.
   */
  error: string | null;

  /**
   * The conversation_id returned by the backend for the current session.
   * Null until the first message has been sent and a response received.
   * Reset to null when clearMessages() is called.
   */
  conversationId: string | null;

  /**
   * Send a question to the backend.
   * Adds the user message immediately, then adds the bot response
   * (or an error bubble) when the API responds.
   */
  handleSend: (question: string) => Promise<void>;

  /** Reset the conversation to its initial empty state */
  clearMessages: () => void;
}

// ── Stable ID generator ───────────────────────────────────────
// crypto.randomUUID() is available in all modern browsers and
// in Node 19+. It generates a UUID v4 — guaranteed unique per call.
// Lives outside the hook so it doesn't get recreated on each render.
function generateId(): string {
  return crypto.randomUUID();
}

// ─────────────────────────────────────────────────────────────
// useChat hook
// ─────────────────────────────────────────────────────────────
export function useChat(): UseChatReturn {

  // ── State declarations ───────────────────────────────────────
  //
  // messages: the full conversation history.
  // An array of Message objects. React re-renders whenever this
  // changes. We always append — never mutate existing entries.
  // Immutability is critical: mutating an existing array item
  // won't trigger a re-render because the array reference stays the same.
  const [messages, setMessages] = useState<Message[]>([]);

  // isLoading: true from the moment the user hits send until
  // the API response (success or error) is fully processed.
  // Drives: typing indicator visibility, input disabled state,
  // send button spinner, preventing double-submits.
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // error: stores the most recent error string, or null if healthy.
  // Separate from the error bubble in messages because it lets
  // parent components display a banner or toast if needed,
  // independently of the chat history.
  const [error, setError] = useState<string | null>(null);

  // conversationId: the UUID returned by the backend for the current
  // conversation session. Null until the first successful response.
  // Forwarded on every subsequent sendMessage call so the backend
  // can load history for this conversation.
  const [conversationId, setConversationId] = useState<string | null>(null);


  // ── handleSend ─────────────────────────────────────────────
  // The core function — orchestrates the entire request lifecycle.
  //
  // useCallback memoizes the function so its reference stays stable
  // across re-renders. Without this, every render of the hook creates
  // a new function object, which would cause ChatInput (which receives
  // onSend as a prop) to re-render unnecessarily on every parent render.
  //
  // The empty dependency array [] means the function is created once
  // and never recreated. This is safe here because handleSend accesses
  // state only through the functional update form (prev => ...), which
  // always reads the latest state regardless of when the function was created.
  const handleSend = useCallback(async (question: string): Promise<void> => {

    // ── Guard: prevent empty or whitespace-only submissions ──
    // Trim here as a safety net — ChatInput also trims before calling,
    // but defensive checks at every boundary are good practice.
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) return;

    // ── Guard: prevent concurrent requests ───────────────────
    // If a request is already in flight, ignore this call.
    // The UI enforces this visually (disabled input), but we
    // enforce it programmatically too as a belt-and-suspenders guard.
    if (isLoading) return;

    // ── Step 1: Clear stale error + set loading ───────────────
    // Reset error before each new request so a previous failure
    // doesn't persist on screen while the new request is running.
    setError(null);
    setIsLoading(true);

    // ── Step 2: Optimistic UI — add user message immediately ──
    // Show the user's message RIGHT NOW, before the API responds.
    // This is called "optimistic UI" — we assume success and update
    // the UI immediately, giving a responsive feel instead of making
    // the user wait for a round-trip before seeing their own message.
    //
    // Functional update form (prev => [...prev, newItem]):
    // CORRECT — always operates on the latest state value.
    // WRONG would be: setMessages([...messages, userMessage])
    // Because `messages` in that closure could be stale if multiple
    // state updates are batched (e.g., React 18 automatic batching).
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      text: trimmedQuestion,
      // new Date() captures exactly when the user submitted —
      // not when the response arrives, which could be seconds later.
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    try {
      // ── Step 3: Make the API call ─────────────────────────
      // sendMessage() is defined in api/chat.ts.
      // It makes a POST /api/v1/chat request with axios and
      // returns a Promise<ChatApiResponse>.
      //
      // await suspends this async function here and yields
      // control back to React's event loop so the UI (typing
      // indicator, disabled input) can render while we wait.
      const response = await sendMessage(trimmedQuestion, conversationId ?? undefined);

      // Store/update the conversation_id so every subsequent turn
      // is associated with the same backend conversation and gets
      // its history loaded correctly.
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
      }

      // ── Step 4: Add the bot's response to the conversation ─
      // response.answer is the AI-generated text.
      // response.sources is the list of documents used.
      const botMessage: Message = {
        id: generateId(),
        role: "bot",
        text: response.answer,

        // sources is optional on the Message type (sources?).
        // We only include it when sources is non-empty so that
        // SourceDocs.tsx renders nothing for "I don't know" answers
        // that have no real sources to cite.
        sources: response.sources.length > 0 ? response.sources : undefined,

        // Timestamp reflects when the response arrived — useful
        // if you ever want to show response time or sort messages.
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, botMessage]);

    } catch (err) {
      // ── Step 5: Handle errors without crashing ────────────
      //
      // Two kinds of errors can reach here:
      //
      // A) AxiosError (network issues, HTTP errors) —
      //    sendMessage() already converts these to plain Error
      //    objects with friendly messages, so we just read .message.
      //
      // B) Unexpected runtime errors — caught by the generic
      //    check below.
      //
      // Strategy: show the error as a bot message bubble so the
      // conversation flow is preserved. The user sees something
      // happened without the app crashing or showing a blank screen.

      // Extract the error message safely.
      // `err instanceof Error` is the correct TypeScript pattern —
      // catch clauses type `err` as `unknown` in strict mode,
      // not `Error`, so you must narrow the type before accessing .message.
      const errorText =
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.";

      // Store the raw error string for external consumers
      // (e.g., a toast notification system in the parent).
      setError(errorText);

      // Create an error bubble in the chat so the conversation
      // thread shows what happened inline. Prefixed with ⚠️ to
      // visually distinguish it from real AI answers.
      const errorMessage: Message = {
        id: generateId(),
        role: "bot",
        text: `⚠️ ${errorText}`,
        timestamp: new Date(),
        // No sources on error messages.
      };

      setMessages((prev) => [...prev, errorMessage]);

    } finally {
      // ── Step 6: Always clear loading state ───────────────
      // finally() runs whether the try block succeeded or threw.
      // This guarantees isLoading is ALWAYS set back to false,
      // even if an unexpected error bypasses the catch block.
      // Without this, the UI could be permanently stuck in a
      // loading state after a rare uncaught exception.
      setIsLoading(false);
    }

  }, [isLoading]);
  // isLoading in the dependency array because we read it directly
  // in the guard clause at the top of the function.


  // ── clearMessages ─────────────────────────────────────────
  // Resets the conversation to initial state.
  // Useful for a "New conversation" or "Clear chat" button.
  // useCallback with [] — no dependencies, always stable reference.
  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
    setConversationId(null);
    // Don't reset isLoading here — if a request is in flight,
    // we don't want to clear the loading state prematurely.
  }, []);


  // ── Return the public API of this hook ────────────────────
  // Only expose what consumers need — internal state setters
  // (setMessages, setIsLoading, setError) are not exported.
  // This is encapsulation: consumers can't accidentally corrupt
  // the state by calling setIsLoading(false) at the wrong time.
  return {
    messages,
    isLoading,
    error,
    conversationId,
    handleSend,
    clearMessages,
  };
}
