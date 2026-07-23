// components/AuthForm.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   A single, togglable form that handles both Register and Login.
//   Receives callbacks from App via props — owns zero auth logic.
//
//   Pure presentation: validates client-side, calls onLogin /
//   onRegister, and shows loading + error states passed in.
// ─────────────────────────────────────────────────────────────

import { useState, type FormEvent } from "react";

interface AuthFormProps {
  /** Called with (email, password) when the login form is submitted */
  onLogin: (email: string, password: string) => Promise<void>;
  /** Called with (email, password) when the register form is submitted */
  onRegister: (email: string, password: string) => Promise<void>;
  /** True while the parent hook's async operation is running */
  isLoading: boolean;
  /** Error message from the parent to display under the form */
  error: string | null;
}

export default function AuthForm({
  onLogin,
  onRegister,
  isLoading,
  error,
}: AuthFormProps) {

  // mode controls which form is shown.
  // "login" is the default — most returning users land here.
  const [mode, setMode] = useState<"login" | "register">("login");

  // Local controlled inputs — only this form cares about them.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // Client-side validation error — separate from the server error
  // passed via props, so both can show simultaneously if needed.
  const [localError, setLocalError] = useState<string | null>(null);


  // ── Switch mode ───────────────────────────────────────────
  function switchMode(newMode: "login" | "register") {
    setMode(newMode);
    // Clear all state when switching so the form starts clean.
    setEmail("");
    setPassword("");
    setConfirmPassword("");
    setLocalError(null);
  }


  // ── Form submit ───────────────────────────────────────────
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLocalError(null);

    // Client-side validation.
    // These checks run before any network call — faster feedback.
    if (!email.trim() || !password) {
      setLocalError("Email and password are required.");
      return;
    }

    if (mode === "register") {
      if (password.length < 8) {
        setLocalError("Password must be at least 8 characters.");
        return;
      }
      if (password !== confirmPassword) {
        setLocalError("Passwords do not match.");
        return;
      }
    }

    try {
      if (mode === "login") {
        await onLogin(email.trim().toLowerCase(), password);
      } else {
        await onRegister(email.trim().toLowerCase(), password);
      }
      // On success, the parent (App.tsx) updates user state
      // and unmounts this form — no redirect needed.
    } catch {
      // The error is displayed via the `error` prop from the parent.
      // We don't need to handle it here.
    }
  }


  const isRegister = mode === "register";

  return (
    // Full-screen centered layout.
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl overflow-hidden">

          {/* Header */}
          <div className="bg-indigo-600 px-6 py-8 text-center">
            <div className="w-14 h-14 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-3">
              <span className="text-3xl" role="img" aria-label="Bot">🤖</span>
            </div>
            <h1 className="text-xl font-bold text-white">Customer Support</h1>
            <p className="text-indigo-200 text-sm mt-1">
              {isRegister ? "Create your account" : "Sign in to continue"}
            </p>
          </div>

          {/* Mode toggle tabs */}
          <div className="flex border-b border-gray-100">
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => switchMode(m)}
                aria-label="Switch authentication mode"
                className={[
                  "flex-1 py-3 text-sm font-medium transition-colors",
                  mode === m
                    // Active tab: indigo text + bottom border indicator
                    ? "text-indigo-600 border-b-2 border-indigo-600"
                    : "text-gray-400 hover:text-gray-600",
                ].join(" ")}
              >
                {m === "login" ? "Sign In" : "Register"}
              </button>
            ))}
          </div>

          {/* Form body */}
          <form noValidate onSubmit={handleSubmit} className="px-6 py-6 space-y-4">

            {/* Email field */}
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                // autoComplete hints to the browser which stored
                // credential to suggest — improves UX significantly.
                autoComplete={isRegister ? "email" : "username"}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                placeholder="you@example.com"
                className="w-full px-4 py-2.5 text-sm border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
                required
              />
            </div>

            {/* Password field */}
            <div>
              <label
                htmlFor="password"
                className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete={isRegister ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                placeholder={isRegister ? "Min 8 characters" : "Your password"}
                className="w-full px-4 py-2.5 text-sm border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
                required
              />
            </div>

            {/* Confirm password — only shown in register mode */}
            {isRegister && (
              <div>
                <label
                  htmlFor="confirmPassword"
                  className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide"
                >
                  Confirm Password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isLoading}
                  placeholder="Repeat your password"
                  className="w-full px-4 py-2.5 text-sm border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
                  required
                />
              </div>
            )}

            {/* Error display — shows both local validation and server errors */}
            {(localError || error) && (
              <div
                role="alert"
                className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700"
              >
                {/* Warning icon */}
                <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                {localError ?? error}
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 text-sm font-semibold bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:bg-indigo-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  {/* Spinner */}
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  {isRegister ? "Creating account…" : "Signing in…"}
                </>
              ) : (
                isRegister ? "Create Account" : "Sign In"
              )}
            </button>

          </form>
        </div>

        {/* Fine print */}
        <p className="text-center text-xs text-gray-400 mt-4">
          Your conversations are private and tied to your account.
        </p>
      </div>
    </div>
  );
}
