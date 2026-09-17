"use client";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "back"] as const;

interface PinPadProps {
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  error?: string | null;
  lockoutSeconds?: number | null;
  /** The pad is also the manager-authorisation pad, where "Sign in" is the wrong word. */
  submitLabel?: string;
}

export function PinPad({
  value,
  onChange,
  onSubmit,
  disabled,
  error,
  lockoutSeconds,
  submitLabel = "Sign in",
}: PinPadProps) {
  const locked = (lockoutSeconds ?? 0) > 0;

  function press(key: (typeof KEYS)[number]) {
    if (disabled || locked) return;
    if (key === "clear") {
      onChange("");
      return;
    }
    if (key === "back") {
      onChange(value.slice(0, -1));
      return;
    }
    if (value.length >= 6) return;
    onChange(value + key);
  }

  return (
    <div className="flex w-full max-w-sm flex-col gap-3">
      <div
        data-testid="pin-display"
        className="num flex min-h-14 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface-2)] text-2xl tracking-[0.3em]"
        aria-label="PIN entry"
      >
        {locked ? "Locked" : "•".repeat(value.length) || "—"}
      </div>
      {error ? <p className="text-center text-sm text-[var(--danger)]">{error}</p> : null}
      {locked ? (
        <p className="text-center text-sm text-[var(--warn)]">Try again in {lockoutSeconds}s</p>
      ) : null}
      <div className="grid grid-cols-3 gap-2">
        {KEYS.map((key) => (
          <button
            key={key}
            type="button"
            data-testid={key === "clear" || key === "back" ? `pin-${key}` : `pin-key-${key}`}
            disabled={disabled || locked}
            onClick={() => press(key)}
            className="flex min-h-14 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] text-lg font-semibold active:bg-[var(--surface-3)] disabled:opacity-40"
          >
            {key === "clear" ? "Clear" : key === "back" ? "⌫" : key}
          </button>
        ))}
      </div>
      <button
        type="button"
        data-testid="pin-submit"
        disabled={disabled || locked || value.length < 4}
        onClick={onSubmit}
        className="flex min-h-16 items-center justify-center rounded-lg bg-[var(--accent)] text-lg font-semibold text-[var(--accent-ink)] disabled:opacity-40"
      >
        {submitLabel}
      </button>
    </div>
  );
}
