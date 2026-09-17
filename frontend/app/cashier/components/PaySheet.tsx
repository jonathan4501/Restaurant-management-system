"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { newIdempotencyKey } from "@/lib/api/client";
import { formatPesewas } from "@/lib/money";

import { AmountPad } from "./AmountPad";
import { problemMessage, recordPayment } from "../lib/api";
import {
  methodLabel,
  needsReference,
  paySheetView,
  PAYMENT_METHODS,
  quickTenders,
  splitEvenly,
} from "../lib/till";
import type { PaymentMethod, PaymentResult } from "../lib/types";

/** The splits a table of four actually asks for. Two taps and nobody does arithmetic out loud. */
const SPLIT_WAYS = [2, 3, 4];

interface PaySheetProps {
  sessionId: string;
  tableNumber: string;
  balancePesewas: number;
  onClose: () => void;
  onPaid: (result: PaymentResult) => void;
}

export function PaySheet({
  sessionId,
  tableNumber,
  balancePesewas,
  onClose,
  onPaid,
}: PaySheetProps) {
  const [method, setMethod] = useState<PaymentMethod>("CASH");
  const [amountPesewas, setAmountPesewas] = useState(balancePesewas);
  const [tenderedPesewas, setTenderedPesewas] = useState(balancePesewas);
  const [reference, setReference] = useState("");
  const [editing, setEditing] = useState<"amount" | "tendered">("amount");
  // Regenerated after every accepted payment: a split is several payments from one open sheet.
  const [paymentId, setPaymentId] = useState(() => newIdempotencyKey());

  const view = paySheetView({ method, amountPesewas, tenderedPesewas, reference }, balancePesewas);
  const cash = method === "CASH";

  const pay = useMutation({
    mutationFn: () =>
      recordPayment(sessionId, {
        id: paymentId,
        method,
        amount_pesewas: view.amountPesewas,
        tendered_pesewas: cash ? view.tenderedPesewas : null,
        external_reference: view.reference,
      }),
    onSuccess: (result) => {
      setPaymentId(newIdempotencyKey());
      setReference("");
      const left = result.balance_pesewas;
      setAmountPesewas(left);
      setTenderedPesewas(left);
      onPaid(result);
    },
  });

  function pickMethod(next: PaymentMethod) {
    setMethod(next);
    // Cash is the only method where the guest hands over more than the amount.
    if (next === "CASH") setTenderedPesewas(Math.max(amountPesewas, tenderedPesewas));
    setEditing("amount");
  }

  function setAmount(next: number) {
    setAmountPesewas(next);
    if (cash && next > tenderedPesewas) setTenderedPesewas(next);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal
      data-testid="pay-sheet"
    >
      <div className="flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
        <header className="flex items-center justify-between gap-4 border-b border-[var(--line)] p-4">
          <div>
            <h2 className="text-2xl font-bold">Table {tableNumber}</h2>
            <p className="text-[var(--ink-2)]">
              Balance <span className="num">{formatPesewas(balancePesewas)}</span>
            </p>
          </div>
          <button
            type="button"
            data-testid="pay-sheet-close"
            onClick={onClose}
            className="min-h-14 rounded-lg border border-[var(--line)] px-5 text-lg"
          >
            Close
          </button>
        </header>

        <div className="grid flex-1 grid-cols-1 gap-4 overflow-y-auto p-4 sm:grid-cols-2">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Payment method">
              {PAYMENT_METHODS.map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={method === option}
                  data-testid={`method-${option}`}
                  onClick={() => pickMethod(option)}
                  className={`min-h-16 rounded-lg px-4 text-lg font-semibold ${
                    method === option
                      ? "bg-[var(--accent)] text-[var(--accent-ink)]"
                      : "border border-[var(--line)] bg-[var(--surface-2)] text-[var(--ink-2)]"
                  }`}
                >
                  {methodLabel(option)}
                </button>
              ))}
            </div>

            <div className="flex flex-col gap-2">
              <p className="text-sm uppercase tracking-wide text-[var(--ink-3)]">Split the bill</p>
              <div className="grid grid-cols-4 gap-2">
                <button
                  type="button"
                  data-testid="split-all"
                  onClick={() => setAmount(balancePesewas)}
                  className="min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] text-lg"
                >
                  All
                </button>
                {SPLIT_WAYS.map((ways) => (
                  <button
                    key={ways}
                    type="button"
                    data-testid={`split-${ways}`}
                    onClick={() => setAmount(splitEvenly(balancePesewas, ways)[0] ?? 0)}
                    className="min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] text-lg"
                  >
                    ÷{ways}
                  </button>
                ))}
              </div>
            </div>

            {needsReference(method) ? (
              <label className="block text-sm text-[var(--ink-2)]">
                Reference
                <input
                  data-testid="pay-reference"
                  value={reference}
                  onChange={(event) => setReference(event.target.value)}
                  placeholder="MP2609 1234 5678"
                  autoCapitalize="characters"
                  className="num mt-1 min-h-14 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-4 text-lg uppercase"
                />
                <span data-testid="pay-reference-normalised" className="num mt-1 block text-[var(--ink-3)]">
                  {view.reference ? `Stored as ${view.reference}` : "Spaces and case do not matter"}
                </span>
              </label>
            ) : null}

            {cash ? (
              <div className="flex flex-col gap-2">
                <p className="text-sm uppercase tracking-wide text-[var(--ink-3)]">Cash given</p>
                <div className="grid grid-cols-2 gap-2">
                  {quickTenders(view.amountPesewas).map((tender) => (
                    <button
                      key={tender}
                      type="button"
                      data-testid={`tender-${tender}`}
                      onClick={() => setTenderedPesewas(tender)}
                      className="num min-h-16 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] text-lg"
                    >
                      {formatPesewas(tender, { symbol: false })}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                data-testid="edit-amount"
                aria-pressed={editing === "amount"}
                onClick={() => setEditing("amount")}
                className={`min-h-16 rounded-lg border px-3 text-left ${
                  editing === "amount"
                    ? "border-[var(--accent)] bg-[var(--surface-3)]"
                    : "border-[var(--line)] bg-[var(--surface-2)]"
                }`}
              >
                <span className="block text-xs uppercase tracking-wide text-[var(--ink-3)]">
                  Paying now
                </span>
                <span data-testid="pay-amount" className="num text-xl font-bold">
                  {formatPesewas(view.amountPesewas)}
                </span>
              </button>
              {cash ? (
                <button
                  type="button"
                  data-testid="edit-tendered"
                  aria-pressed={editing === "tendered"}
                  onClick={() => setEditing("tendered")}
                  className={`min-h-16 rounded-lg border px-3 text-left ${
                    editing === "tendered"
                      ? "border-[var(--accent)] bg-[var(--surface-3)]"
                      : "border-[var(--line)] bg-[var(--surface-2)]"
                  }`}
                >
                  <span className="block text-xs uppercase tracking-wide text-[var(--ink-3)]">
                    Cash given
                  </span>
                  <span data-testid="pay-tendered" className="num text-xl font-bold">
                    {formatPesewas(view.tenderedPesewas ?? 0)}
                  </span>
                </button>
              ) : null}
            </div>

            <AmountPad
              label={editing === "amount" ? "Paying now" : "Cash given"}
              testId="pay-pad"
              valuePesewas={editing === "amount" ? view.amountPesewas : (view.tenderedPesewas ?? 0)}
              onChange={editing === "amount" ? setAmount : setTenderedPesewas}
            />

            {cash && view.changePesewas !== null ? (
              <div className="rounded-xl border-2 border-[var(--accent-line)] bg-[var(--accent-soft)] p-4">
                <p className="text-sm uppercase tracking-wide text-[var(--ink-3)]">Change</p>
                <p data-testid="pay-change" className="num text-6xl font-bold text-[var(--accent)]">
                  {formatPesewas(view.changePesewas)}
                </p>
              </div>
            ) : null}
          </div>
        </div>

        <footer className="border-t border-[var(--line)] p-4">
          {pay.isError ? (
            <p data-testid="pay-error" className="mb-2 text-[var(--danger)]">
              {problemMessage(pay.error, "The payment did not go through.")}
            </p>
          ) : null}
          {view.blockedReason ? (
            <p data-testid="pay-blocked" className="mb-2 text-[var(--warn)]">
              {view.blockedReason}
            </p>
          ) : (
            <p className="mb-2 text-[var(--ink-2)]">
              {view.settles ? (
                "This settles the bill."
              ) : (
                <>
                  <span className="num">{formatPesewas(view.balanceAfterPesewas)}</span> will still
                  be owing.
                </>
              )}
            </p>
          )}
          <button
            type="button"
            data-testid="pay-submit"
            disabled={pay.isPending || view.blockedReason !== null}
            onClick={() => pay.mutate()}
            className="min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)] disabled:opacity-40"
          >
            {pay.isPending
              ? "Recording…"
              : `Take ${formatPesewas(view.amountPesewas)} by ${methodLabel(method)}`}
          </button>
        </footer>
      </div>
    </div>
  );
}
