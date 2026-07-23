// App.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Root component — decides what to render based on auth state:
//
//   isInitialised = false  →  blank/spinner (startup token check)
//   user = null            →  AuthForm (login / register)
//   user = logged in       →  Chat interface
//
//   All state lives in hooks. This file is layout + routing only.
// ─────────────────────────────────────────────────────────────

import { useState } from "react";
import { useAuth } from "./hooks/useAuth";
import { useChat } from "./hooks/useChat";
import { useUpload } from "./hooks/useUpload";
import AuthForm from "./components/AuthForm";
import ChatHeader from "./components/ChatHeader";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import UploadPanel from "./components/UploadPanel";

export default function App() {

  // ── Auth state ────────────────────────────────────────────
  // useAuth() is the single source of truth for who is logged in.
  const { user, isLoading: authLoading, error: authError, isInitialised, login, register, logout } = useAuth();

  // ── Chat state ────────────────────────────────────────────
  const { messages, isLoading: chatLoading, handleSend, clearMessages } = useChat();

  // ── Upload state ──────────────────────────────────────────
  const { fileStates, isUploading, isDone, addFiles, removeFile, uploadAll, reset } = useUpload();

  // ── Upload panel visibility ───────────────────────────────
  const [uploadOpen, setUploadOpen] = useState(false);


  // ── Phase 1: Startup — token verification in progress ─────
  // Show a neutral loading screen while the startup getMe()
  // call completes. This prevents a flash of the login form
  // for users with valid sessions.
  if (!isInitialised) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          {/* Indigo spinner */}
          <svg
            className="w-10 h-10 text-indigo-600 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
            aria-label="Loading"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <p className="text-sm text-gray-500">Loading…</p>
        </div>
      </div>
    );
  }


  // ── Phase 2: Not logged in — show auth form ───────────────
  // user === null means either no stored tokens were found on
  // startup, or the tokens were invalid/expired.
  if (!user) {
    return (
      <AuthForm
        onLogin={login}
        onRegister={register}
        isLoading={authLoading}
        error={authError}
      />
    );
  }


  // ── Phase 3: Logged in — show chat interface ──────────────
  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">

      {/* Chat card */}
      <div className="relative w-full max-w-2xl h-[600px] bg-white rounded-2xl shadow-xl flex flex-col overflow-hidden">

        {/* Header — passes logout and user email */}
        <ChatHeader
          onClear={clearMessages}
          onUploadClick={() => setUploadOpen(true)}
          onLogout={logout}
          userEmail={user.email}
        />

        {/* Message area */}
        <div className="flex-1 min-h-0 flex flex-col bg-gray-50">
          <ChatWindow messages={messages} isLoading={chatLoading} />
        </div>

        {/* Input bar */}
        <ChatInput onSend={handleSend} isLoading={chatLoading} />

        {/* Upload panel overlay */}
        {uploadOpen && (
          <UploadPanel
            fileStates={fileStates}
            isUploading={isUploading}
            isDone={isDone}
            onAddFiles={addFiles}
            onRemoveFile={removeFile}
            onUpload={uploadAll}
            onReset={reset}
            onClose={() => { if (!isUploading) setUploadOpen(false); }}
          />
        )}
      </div>
    </div>
  );
}
