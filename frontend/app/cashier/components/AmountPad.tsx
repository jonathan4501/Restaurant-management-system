"use client";

import { formatPesewas } from "@/lib/money";

import { padPop, padPush } from "../lib/till";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "00", "0", "back"] as const;

interface AmountPadProps {
  /** Integer pesewas. The pad never holds anything else. */
  valuePesewas: number;
  onChange: (next: number) => void;
  label: string;
  testId: string;
}

/**
 * The only way a cashier enters money. There is no text input behind it, so there is no way to
 * type "133.5" and mean GH₵ 133.50 — the keypad shifts pesewas in from the right instead.
 */
export function AmountPad({ valuePesewas, onChange, label, testId }: AmountPadProps) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="text-sm uppercase tracking-wide text-[var(--ink-3)]">{label}</p>
        <p data-testid={`${testId}-display`} className="num text-4xl font-bold">
          {formatPesewas(valuePesewas)}
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {KEYS.map((key) => (
          <button
            key={key}
            type="button"
            data-testid={`${testId}-${key}`}
            onClick={() => onChange(key === "back" ? padPop(valuePesewas) : padPush(valuePesewas, key))}
            className="flex min-h-16 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface-2)] text-2xl font-semibold active:bg-[var(--surface-3)]"
          >
            {key === "back" ? "⌫" : key}
          </button>
        ))}
      </div>
      <button
        type="button"
        data-testid={`${testId}-clear`}
        onClick={() => onChange(0)}
        className="min-h-14 rounded-lg border border-[var(--line)] px-4 text-lg text-[var(--ink-2)]"
      >
        Clear
      </button>
    </div>
  );
}
