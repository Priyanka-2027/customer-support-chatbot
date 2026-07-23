// components/TypingIndicator.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Show an animated "bot is typing" indicator while waiting
//   for the Gemini API response. Pure presentational component —
//   no props, no state. Visibility is controlled by the parent
//   (App.tsx) by mounting/unmounting it conditionally.
// ─────────────────────────────────────────────────────────────

export default function TypingIndicator() {
  return (
    // Same left-aligned layout as a bot MessageBubble
    <div className="flex w-full justify-start mb-3">

      {/* Bot avatar — matches MessageBubble's bot avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center mr-2">
        <span className="text-white text-sm" role="img" aria-label="Bot">🤖</span>
      </div>

      {/* Bubble with three animated dots */}
      <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
        <div className="flex items-center gap-1" aria-label="Bot is typing">
          {/* Each dot is a small circle with a bounce animation.
              animation-delay staggers the dots so they bounce
              in sequence rather than all at once. */}
          <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}
