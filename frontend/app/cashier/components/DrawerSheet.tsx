"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { AuthoriseSheet } from "@/components/AuthoriseSheet";
import { formatPesewas } from "@/lib/money";

import { AmountPad } from "./AmountPad";
import { problemMessage, recordDrawerMovement } from "../lib/api";
import type { DrawerKind } from "../lib/types";

const KINDS: { kind: DrawerKind; label: string; blurb: string }[] = [
  { kind: "NO_SALE", label: "No sale", blurb: "Opening the drawer to make change." },
  { kind: "PAID_OUT", label: "Paid out", blurb: "Cash leaving the drawer — a supplier, a taxi." },
  { kind: "PAID_IN", label: "Paid in", blurb: "Cash going into the drawer that is not a payment." },
];

interface DrawerSheetProps {
  shiftId: string;
  onClose: () => void;
  onDone: (message: string) => void;
}

/**
 * Cash moving with no sale behind it is the easiest money in the building to take, so every
 * movement needs a manager's PIN and a reason code, and each one writes an event naming both.
 */
export function DrawerSheet({ shiftId, onClose, onDone }: DrawerSheetProps) {
  const [kind, setKind] = useState<DrawerKind>("NO_SALE");
  const [amountPesewas, setAmountPesewas] = useState(0);
  const [authorising, setAuthorising] = useState(false);

  const record = useMutation({
    mutationFn: ({ token, reasonCode }: { token: string; reasonCode: string }) =>
      recordDrawerMovement(
        shiftId,
        { kind, amount_pesewas: kind === "NO_SALE" ? 0 : amountPesewas, note: "" },
        { token, reason_code: reasonCode },
      ),
    onSuccess: () => {
      const label = KINDS.find((k) => k.kind === kind)?.label ?? "Movement";
      onDone(kind === "NO_SALE" ? "Drawer opened" : `${label} ${formatPesewas(amountPesewas)}`);
      onClose();
    },
  });

  const needsAmount = kind !== "NO_SALE";
  const blocked = needsAmount && amountPesewas <= 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal
      data-testid="drawer-sheet"
    >
      <div className="flex w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
        <header className="flex items-center justify-between gap-4 border-b border-[var(--line)] p-4">
          <h2 className="text-2xl font-bold">Drawer</h2>
          <button
            type="button"
            data-testid="drawer-close"
            onClick={onClose}
            className="min-h-14 rounded-lg border border-[var(--line)] px-5 text-lg"
          >
            Close
          </button>
        </header>

        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          <div className="flex flex-col gap-2">
            {KINDS.map((option) => (
              <button
                key={option.kind}
                type="button"
                data-testid={`drawer-${option.kind}`}
                aria-pressed={kind === option.kind}
                onClick={() => setKind(option.kind)}
                className={`min-h-16 rounded-lg border px-4 py-2 text-left ${
                  kind === option.kind
                    ? "border-[var(--accent)] bg-[var(--surface-3)]"
                    : "border-[var(--line)] bg-[var(--surface-2)]"
                }`}
              >
                <span className="block text-lg font-semibold">{option.label}</span>
                <span className="block text-sm text-[var(--ink-3)]">{option.blurb}</span>
              </button>
            ))}
          </div>

          {needsAmount ? (
            <AmountPad
              label="Amount"
              testId="drawer-amount"
              valuePesewas={amountPesewas}
              onChange={setAmountPesewas}
            />
          ) : null}

          {record.isError ? (
            <p data-testid="drawer-error" className="text-[var(--danger)]">
              {problemMessage(record.error, "The drawer movement was not recorded.")}
            </p>
          ) : null}
        </div>

        <footer className="border-t border-[var(--line)] p-4">
          <button
            type="button"
            data-testid="drawer-submit"
            disabled={blocked || record.isPending}
            onClick={() => setAuthorising(true)}
            className="min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)] disabled:opacity-40"
          >
            {record.isPending ? "Recording…" : "Manager PIN to continue"}
          </button>
        </footer>
      </div>

      <AuthoriseSheet
        purpose="DRAWER_MOVEMENT"
        open={authorising}
        onClose={() => setAuthorising(false)}
        onAuthorised={(token, reasonCode) => record.mutate({ token, reasonCode })}
      />
    </div>
  );
}
