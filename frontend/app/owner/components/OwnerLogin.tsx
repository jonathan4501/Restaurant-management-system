"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { ConnectivityBadge } from "@/components/ConnectivityBadge";

import { ownerLogin, ownerTotp, problemMessage } from "../lib/api";

interface Props {
  onAuthenticated: () => void;
}

export function OwnerLogin({ onAuthenticated }: Props) {
  const [step, setStep] = useState<"password" | "totp">("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const login = useMutation({
    mutationFn: () => ownerLogin(email.trim(), password),
    onSuccess: () => {
      setError(null);
      setStep("totp");
      setCode("");
    },
    onError: (err) => setError(problemMessage(err, "Could not sign in")),
  });

  const totp = useMutation({
    mutationFn: () => ownerTotp(code.trim()),
    onSuccess: () => {
      setError(null);
      onAuthenticated();
    },
    onError: (err) => setError(problemMessage(err, "Invalid code")),
  });

  return (
    <main className="staff-shell staff-theme flex min-h-screen flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-start justify-between gap-3">
          <div>
            <p className="wordmark text-xl">RENZY</p>
            <h1 className="text-2xl font-semibold">Owner</h1>
            <p className="mt-1 text-sm text-[var(--ink-3)]">
              {step === "password" ? "Email and password, then your authenticator code." : "Enter the 6-digit code from your authenticator."}
            </p>
          </div>
          <ConnectivityBadge />
        </div>

        {step === "password" ? (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void login.mutate();
            }}
          >
            <label className="block text-sm font-medium">
              Email
              <input
                data-testid="owner-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3 text-base"
              />
            </label>
            <label className="block text-sm font-medium">
              Password
              <input
                data-testid="owner-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3 text-base"
              />
            </label>
            <button
              type="submit"
              data-testid="owner-login-submit"
              disabled={login.isPending || email.trim().length < 3 || password.length < 8}
              className="flex min-h-16 w-full items-center justify-center rounded-lg bg-[var(--accent)] text-lg font-semibold text-[var(--accent-ink)] disabled:opacity-40"
            >
              {login.isPending ? "Checking…" : "Continue"}
            </button>
          </form>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void totp.mutate();
            }}
          >
            <label className="block text-sm font-medium">
              Authenticator code
              <input
                data-testid="owner-totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                className="mt-1 w-full min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3 text-center text-2xl tracking-[0.4em]"
              />
            </label>
            <button
              type="submit"
              data-testid="owner-totp-submit"
              disabled={totp.isPending || code.length < 6}
              className="flex min-h-16 w-full items-center justify-center rounded-lg bg-[var(--accent)] text-lg font-semibold text-[var(--accent-ink)] disabled:opacity-40"
            >
              {totp.isPending ? "Verifying…" : "Open dashboard"}
            </button>
            <button
              type="button"
              className="min-h-14 text-sm text-[var(--accent)]"
              onClick={() => {
                setStep("password");
                setError(null);
              }}
            >
              ← Back
            </button>
          </form>
        )}

        {error ? (
          <p role="alert" data-testid="owner-login-error" className="mt-4 text-sm text-[var(--danger)]">
            {error}
          </p>
        ) : null}
      </div>
    </main>
  );
}
