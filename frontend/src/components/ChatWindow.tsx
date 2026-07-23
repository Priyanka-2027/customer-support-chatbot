// components/ChatWindow.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Render the scrollable list of messages.
//   Auto-scroll to the latest message whenever messages change.
//   Show the empty state when no messages exist yet.
//   Show the typing indicator while waiting for a bot response.
// ─────────────────────────────────────────────────────────────

import { useEffect, useRef } from "react";
import type { Message } from "../types";
import MessageBubble from "./MessageBubble";
import SourceDocs from "./SourceDocs";
import TypingIndicator from "./TypingIndicator";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
}

export default function ChatWindow({ messages, isLoading }: ChatWindowProps) {
  // useRef gives us a stable reference to the bottom-sentinel div
  // so we can call scrollIntoView() on it without triggering a render.
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever messages are added OR when
  // loading starts (so the typing indicator is visible).
  // The dependency array [messages, isLoading] means this effect
  // runs after every render where either value changed.
  useEffect(() => {
    const node = bottomRef.current;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isLoading]);

  return (
    // flex-1 makes this div fill all available vertical space
    // between the header and the input box.
    // overflow-y-auto enables scrolling within this container.
    // The parent (App) must have a fixed height for this to work.
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">

      {/* ── Empty state ─────────────────────────────────── */}
      {/* Shown only when there are no messages yet */}
      {messages.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-full text-center py-16">
          <div className="w-16 h-16 bg-indigo-100 rounded-full flex items-center justify-center mb-4">
            <span className="text-3xl" role="img" aria-label="Chat">💬</span>
          </div>
          <h2 className="text-lg font-semibold text-gray-700 mb-2">
            How can I help you today?
          </h2>
          <p className="text-sm text-gray-400 max-w-xs">
            Ask me anything about our products, policies, or services.
          </p>
        </div>
      )}

      {/* ── Message list ─────────────────────────────────── */}
      {messages.map((message) => (
        // React.Fragment with key lets us group MessageBubble +
        // SourceDocs under one key without adding a DOM wrapper div
        // that would affect the layout.
        <div key={message.id}>
          <MessageBubble message={message} />
          {/* Sources are only shown for bot messages that have them */}
          {message.role === "bot" && message.sources && (
            <SourceDocs sources={message.sources} />
          )}
        </div>
      ))}

      {/* ── Typing indicator ─────────────────────────────── */}
      {/* Mounted while waiting for the API response.
          Unmounted when the response arrives and the bot message
          is added to the messages array. */}
      {isLoading && <TypingIndicator />}

      {/* Invisible sentinel div at the bottom.
          scrollIntoView() on this element scrolls the window
          to show the latest content. */}
      <div ref={bottomRef} />
    </div>
  );
}
