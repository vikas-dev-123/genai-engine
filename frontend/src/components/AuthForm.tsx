import { FormEvent, useMemo, useState } from "react";
import { Lock, Mail, User } from "lucide-react";

import { useAuthStore } from "../store/authStore";

type Mode = "signin" | "register";

export function AuthForm() {
  const login = useAuthStore((s) => s.login);
  const register = useAuthStore((s) => s.register);

  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const emailValid = useMemo(() => /.+@.+\..+/.test(email), [email]);
  const canSubmitRegister = name.trim().length >= 2 && password.length >= 8 && password === confirm;
  const canSubmitSignIn = emailValid && password.length >= 1;

  const handleSubmit = async (evt: FormEvent) => {
    evt.preventDefault();
    setError(null);
    if (mode === "register") {
      if (!emailValid) {
        setError("Enter a valid email.");
        return;
      }
      if (password.length < 8) {
        setError("Password must be at least 8 characters.");
        return;
      }
      if (password !== confirm) {
        setError("Passwords do not match.");
        return;
      }
      setLoading(true);
      try {
        await register(email.trim(), password, name.trim());
      } catch (err) {
        setError("Registration failed. Try a different email.");
      } finally {
        setLoading(false);
      }
    } else {
      if (!canSubmitSignIn) {
        setError("Enter your credentials.");
        return;
      }
      setLoading(true);
      try {
        await login(email.trim(), password);
      } catch (err) {
        setError("Invalid email or password.");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="min-h-screen bg-jarvis-bg flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-jarvis-border bg-jarvis-surface/80 p-8 shadow-[0_0_40px_rgba(108,99,255,0.15)] backdrop-blur">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-semibold tracking-[0.3em] text-jarvis-accent drop-shadow-[0_0_18px_rgba(108,99,255,0.65)]">
            JARVIS
          </h1>
          <p className="mt-2 text-sm text-jarvis-muted">Personal AI console</p>
        </div>

        <div className="flex rounded-lg bg-jarvis-bg border border-jarvis-border p-1 mb-6">
          <button
            type="button"
            onClick={() => setMode("signin")}
            className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
              mode === "signin"
                ? "bg-jarvis-accent/20 text-jarvis-text"
                : "text-jarvis-muted hover:text-jarvis-text"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => setMode("register")}
            className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
              mode === "register"
                ? "bg-jarvis-accent/20 text-jarvis-text"
                : "text-jarvis-muted hover:text-jarvis-text"
            }`}
          >
            Create Account
          </button>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          {mode === "register" && (
            <label className="block">
              <span className="text-xs text-jarvis-muted">Name</span>
              <div className="mt-1 flex items-center gap-2 rounded-lg border border-jarvis-border bg-jarvis-bg px-3 py-2">
                <User className="h-4 w-4 text-jarvis-muted" />
                <input
                  className="w-full bg-transparent text-sm text-jarvis-text outline-none"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ada Lovelace"
                  autoComplete="name"
                />
              </div>
            </label>
          )}

          <label className="block">
            <span className="text-xs text-jarvis-muted">Email</span>
            <div className="mt-1 flex items-center gap-2 rounded-lg border border-jarvis-border bg-jarvis-bg px-3 py-2">
              <Mail className="h-4 w-4 text-jarvis-muted" />
              <input
                className="w-full bg-transparent text-sm text-jarvis-text outline-none"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>
          </label>

          <label className="block">
            <span className="text-xs text-jarvis-muted">Password</span>
            <div className="mt-1 flex items-center gap-2 rounded-lg border border-jarvis-border bg-jarvis-bg px-3 py-2">
              <Lock className="h-4 w-4 text-jarvis-muted" />
              <input
                className="w-full bg-transparent text-sm text-jarvis-text outline-none"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete={mode === "register" ? "new-password" : "current-password"}
              />
            </div>
          </label>

          {mode === "register" && (
            <label className="block">
              <span className="text-xs text-jarvis-muted">Confirm password</span>
              <div className="mt-1 flex items-center gap-2 rounded-lg border border-jarvis-border bg-jarvis-bg px-3 py-2">
                <Lock className="h-4 w-4 text-jarvis-muted" />
                <input
                  className="w-full bg-transparent text-sm text-jarvis-text outline-none"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="new-password"
                />
              </div>
            </label>
          )}

          {error && (
            <div className="rounded-md border border-jarvis-danger/60 bg-jarvis-danger/10 px-3 py-2 text-sm text-jarvis-danger">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={
              loading ||
              (mode === "register" ? !canSubmitRegister : !canSubmitSignIn || !emailValid)
            }
            className="relative w-full overflow-hidden rounded-lg bg-jarvis-accent py-2.5 text-sm font-semibold text-white shadow-[0_0_24px_rgba(108,99,255,0.35)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading && (
              <span className="absolute inset-0 flex items-center justify-center bg-jarvis-accent/80">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/50 border-t-white" />
              </span>
            )}
            <span className={loading ? "opacity-0" : ""}>{mode === "register" ? "Create" : "Enter"}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
