"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { AuthoriseSheet } from "@/components/AuthoriseSheet";
import { formatPesewas } from "@/lib/money";

import { AmountPad } from "./AmountPad";
import { applyDiscount, problemMessage } from "../lib/api";

const PERCENTS = [5, 10, 20, 50];

interface DiscountSheetProps {
  orderId: string;
  orderLabel: string;
  orderTotalPesewas: number;
  onClose: () => void;
  onDone: (message: string) => void;
}

/**
 * Money coming off a bill is money out of the till, so it is a manager's decision with a reason
 * code attached — the owner's variance report reads exactly these events.
 */
export function DiscountSheet({
  orderId,
  orderLabel,
  orderTotalPesewas,
  onClose,
  onDone,
}: DiscountSheetProps) {
  const [kind, setKind] = useState<"PERCENT" | "AMOUNT">("PERCENT");
  const [percent, setPercent] = useState(10);
  const [amountPesewas, setAmountPesewas] = useState(0);
  const [authorising, setAuthorising] = useState(false);

  const value = kind === "PERCENT" ? percent : amountPesewas;
  // Shown so the cashier sees the cedis before the manager is called over, not after.
  const previewPesewas =
    kind === "PERCENT" ? Math.floor((orderTotalPesewas * percent) / 100) : amountPesewas;
  const blocked = value <= 0 || previewPesewas > orderTotalPesewas;

  const apply = useMutation({
    mutationFn: ({ token, reasonCode }: { token: string; reasonCode: string }) =>
      applyDiscount(orderId, { kind, value }, { token, reason_code: reasonCode }),
    onSuccess: () => {
      onDone(`${formatPesewas(previewPesewas)} off ${orderLabel}`);
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal
      data-testid="discount-sheet"
    >
      <div className="flex w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
        <header className="flex items-center justify-between gap-4 border-b border-[var(--line)] p-4">
          <div>
            <h2 className="text-2xl font-bold">Discount</h2>
            <p className="text-[var(--ink-2)]">
              {orderLabel} · <span className="num">{formatPesewas(orderTotalPesewas)}</span>
            </p>
          </div>
          <button
            type="button"
            data-testid="discount-close"
            onClick={onClose}
            className="min-h-14 rounded-lg border border-[var(--line)] px-5 text-lg"
          >
            Close
          </button>
        </header>

        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          <div className="grid grid-cols-2 gap-2">
            {(["PERCENT", "AMOUNT"] as const).map((option) => (
              <button
                key={option}
                type="button"
                data-testid={`discount-kind-${option}`}
                aria-pressed={kind === option}
                onClick={() => setKind(option)}
                className={`min-h-16 rounded-lg text-lg font-semibold ${
                  kind === option
                    ? "bg-[var(--accent)] text-[var(--accent-ink)]"
                    : "border border-[var(--line)] bg-[var(--surface-2)] text-[var(--ink-2)]"
                }`}
              >
                {option === "PERCENT" ? "Percent" : "Amount"}
              </button>
            ))}
          </div>

          {kind === "PERCENT" ? (
            <div className="grid grid-cols-4 gap-2">
              {PERCENTS.map((option) => (
                <button
                  key={option}
                  type="button"
                  data-testid={`discount-percent-${option}`}
                  aria-pressed={percent === option}
                  onClick={() => setPercent(option)}
                  className={`num min-h-16 rounded-lg border text-xl ${
                    percent === option
                      ? "border-[var(--accent)] bg-[var(--surface-3)]"
                      : "border-[var(--line)] bg-[var(--surface-2)]"
                  }`}
                >
                  {option}%
                </button>
              ))}
            </div>
          ) : (
            <AmountPad
              label="Take off"
              testId="discount-amount"
              valuePesewas={amountPesewas}
              onChange={setAmountPesewas}
            />
          )}

          <p className="text-lg">
            Comes off:{" "}
            <span data-testid="discount-preview" className="num font-bold">
              {formatPesewas(previewPesewas)}
            </span>
          </p>

          {apply.isError ? (
            <p data-testid="discount-error" className="text-[var(--danger)]">
              {problemMessage(apply.error, "The discount was not applied.")}
            </p>
          ) : null}
        </div>

        <footer className="border-t border-[var(--line)] p-4">
          <button
            type="button"
            data-testid="discount-submit"
            disabled={blocked || apply.isPending}
            onClick={() => setAuthorising(true)}
            className="min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)] disabled:opacity-40"
          >
            {apply.isPending ? "Applying…" : "Manager PIN to continue"}
          </button>
        </footer>
      </div>

      <AuthoriseSheet
        purpose="DISCOUNT"
        open={authorising}
        onClose={() => setAuthorising(false)}
        onAuthorised={(token, reasonCode) => apply.mutate({ token, reasonCode })}
      />
    </div>
  );
}
