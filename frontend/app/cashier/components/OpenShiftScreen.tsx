"use client";

import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { newIdempotencyKey } from "@/lib/api/client";
import { formatPesewas } from "@/lib/money";

import { AmountPad } from "./AmountPad";
import { openShift, problemMessage } from "../lib/api";
import type { Shift } from "../lib/types";

/** The floats a manager actually hands over at the start of service. */
const COMMON_FLOATS = [10_000, 20_000, 50_000];

interface OpenShiftScreenProps {
  onOpened: (shift: Shift) => void;
  cashierName: string;
}

/**
 * Nothing can be paid until a shift is open, because until then there is no drawer to reconcile
 * against. This is the whole screen, not a banner — there is exactly one thing to do.
 */
export function OpenShiftScreen({ onOpened, cashierName }: OpenShiftScreenProps) {
  const [floatPesewas, setFloatPesewas] = useState(0);
  // The shift id is the idempotency anchor: a double-tap on a slow connection must reuse it.
  const shiftId = useRef(newIdempotencyKey());

  const open = useMutation({
    mutationFn: () => openShift(shiftId.current, floatPesewas),
    onSuccess: onOpened,
  });

  return (
    <main
      className="staff-shell staff-theme flex min-h-screen items-center justify-center p-4"
      data-testid="open-shift"
    >
      <div className="w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
        <h1 className="text-2xl font-bold">Open the till</h1>
        <p className="mt-1 mb-5 text-[var(--ink-2)]">
          {cashierName}, count the float in the drawer before you take a single payment.
        </p>

        <AmountPad
          label="Opening float"
          testId="float"
          valuePesewas={floatPesewas}
          onChange={setFloatPesewas}
        />

        <div className="mt-3 grid grid-cols-3 gap-2">
          {COMMON_FLOATS.map((amount) => (
            <button
              key={amount}
              type="button"
              data-testid={`float-quick-${amount}`}
              onClick={() => setFloatPesewas(amount)}
              className="num min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] text-lg"
            >
              {formatPesewas(amount, { symbol: false })}
            </button>
          ))}
        </div>

        {open.isError ? (
          <p data-testid="open-shift-error" className="mt-3 text-[var(--danger)]">
            {problemMessage(open.error, "Could not open the shift.")}
          </p>
        ) : null}

        <button
          type="button"
          data-testid="open-shift-submit"
          disabled={open.isPending}
          onClick={() => open.mutate()}
          className="mt-4 min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)] disabled:opacity-40"
        >
          {open.isPending ? "Opening…" : "Open shift"}
        </button>
      </div>
    </main>
  );
}
