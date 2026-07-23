// components/ChatHeader.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Header bar — bot name, online status, user email, action buttons.
//   Receives all callbacks as props. Owns zero logic.
// ─────────────────────────────────────────────────────────────

interface ChatHeaderProps {
  onClear: () => void;
  onUploadClick: () => void;
  onLogout: () => void;
  /** Email of the currently logged-in user */
  userEmail: string;
}

export default function ChatHeader({
  onClear,
  onUploadClick,
  onLogout,
  userEmail,
}: ChatHeaderProps) {
  return (
    <div className="flex items-center justify-between px-4 py-3 bg-indigo-600 shadow-sm flex-shrink-0">

      {/* Left: avatar + name + online dot */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
          <span className="text-lg" role="img" aria-label="Support Bot">🤖</span>
        </div>
        <div>
          <h1 className="text-sm font-semibold text-white leading-tight">
            Customer Support
          </h1>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs text-indigo-200">Online</span>
          </div>
        </div>
      </div>

      {/* Right: user email + action buttons */}
      <div className="flex items-center gap-1">

        {/* Logged-in user email — truncated if too long */}
        <span
          className="text-xs text-indigo-200 max-w-[120px] truncate hidden sm:block"
          title={userEmail}
        >
          {userEmail}
        </span>

        <span className="text-indigo-400 text-xs mx-1">|</span>

        {/* Upload docs */}
        <button
          onClick={onUploadClick}
          className="flex items-center gap-1.5 text-xs text-indigo-200 hover:text-white transition-colors px-2 py-1.5 rounded-lg hover:bg-white/10"
          aria-label="Upload PDF documents"
          title="Upload documents"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <span className="hidden sm:inline">Upload</span>
        </button>

        {/* New chat */}
        <button
          onClick={onClear}
          className="text-xs text-indigo-200 hover:text-white transition-colors px-2 py-1.5 rounded-lg hover:bg-white/10"
          aria-label="Start a new conversation"
          title="New chat"
        >
          New chat
        </button>

        {/* Logout */}
        <button
          onClick={onLogout}
          className="text-xs text-indigo-200 hover:text-red-300 transition-colors px-2 py-1.5 rounded-lg hover:bg-white/10"
          aria-label="Sign out"
          title="Sign out"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
        </button>
      </div>
    </div>
  );
}
