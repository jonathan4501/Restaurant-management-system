"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { formatPesewas } from "@/lib/money";

import { AmountPad } from "./AmountPad";
import { closeShift, fetchZReport, problemMessage } from "../lib/api";
import { methodLabel } from "../lib/till";
import type { PaymentMethod, Shift } from "../lib/types";

interface CloseShiftSheetProps {
  shift: Shift;
  onClose: () => void;
  onClosed: () => void;
}

/**
 * Closing is two screens on purpose. The cashier counts the drawer and declares it BEFORE the
 * expected figure is on the glass; showing expected first turns the count into a copy exercise and
 * the variance number stops meaning anything.
 */
export function CloseShiftSheet({ shift, onClose, onClosed }: CloseShiftSheetProps) {
  const [declaredPesewas, setDeclaredPesewas] = useState(0);
  const [note, setNote] = useState("");
  const [closedShiftId, setClosedShiftId] = useState<string | null>(null);

  const close = useMutation({
    mutationFn: () => closeShift(shift.id, declaredPesewas, note),
    onSuccess: () => setClosedShiftId(shift.id),
  });

  const report = useQuery({
    queryKey: ["shift", "z-report", closedShiftId],
    enabled: closedShiftId !== null,
    queryFn: () => fetchZReport(closedShiftId as string),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal
      data-testid="close-shift"
    >
      <div className="flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
        <header className="flex items-center justify-between gap-4 border-b border-[var(--line)] p-4">
          <h2 className="text-2xl font-bold">{closedShiftId ? "Z-report" : "Count the drawer"}</h2>
          <button
            type="button"
            data-testid="close-shift-dismiss"
            onClick={closedShiftId ? onClosed : onClose}
            className="min-h-14 rounded-lg border border-[var(--line)] px-5 text-lg"
          >
            {closedShiftId ? "Done" : "Cancel"}
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {closedShiftId ? (
            <ZReportBody report={report.data} loading={report.isLoading} />
          ) : (
            <CountBody
              declaredPesewas={declaredPesewas}
              onDeclaredChange={setDeclaredPesewas}
              note={note}
              onNoteChange={setNote}
              openingFloatPesewas={shift.opening_float_pesewas}
            />
          )}

          {close.isError ? (
            <p data-testid="close-shift-error" className="mt-3 text-[var(--danger)]">
              {problemMessage(close.error, "Could not close the shift.")}
            </p>
          ) : null}
        </div>

        {closedShiftId ? null : (
          <footer className="border-t border-[var(--line)] p-4">
            <button
              type="button"
              data-testid="close-shift-submit"
              disabled={close.isPending}
              onClick={() => close.mutate()}
              className="min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)] disabled:opacity-40"
            >
              {close.isPending ? "Closing…" : "Declare and close the shift"}
            </button>
          </footer>
        )}
      </div>
    </div>
  );
}

interface CountBodyProps {
  declaredPesewas: number;
  onDeclaredChange: (next: number) => void;
  note: string;
  onNoteChange: (next: string) => void;
  openingFloatPesewas: number;
}

function CountBody({
  declaredPesewas,
  onDeclaredChange,
  note,
  onNoteChange,
  openingFloatPesewas,
}: CountBodyProps) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[var(--ink-2)]">
        Count every note and coin in the drawer, including the{" "}
        <span className="num">{formatPesewas(openingFloatPesewas)}</span> float. The till will show
        you what it expected once you have declared.
      </p>
      <AmountPad
        label="Cash counted"
        testId="declared"
        valuePesewas={declaredPesewas}
        onChange={onDeclaredChange}
      />
      <label className="block text-sm text-[var(--ink-2)]">
        Note (optional)
        <input
          data-testid="close-shift-note"
          value={note}
          onChange={(event) => onNoteChange(event.target.value)}
          placeholder="Anything the owner should know"
          className="mt-1 min-h-14 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-4 text-lg"
        />
      </label>
    </div>
  );
}

function ZReportBody({ report, loading }: { report?: ZReportShape; loading: boolean }) {
  if (loading || !report) return <p className="p-4 text-lg">Adding it up…</p>;

  const variance = report.variance_pesewas ?? 0;
  const balanced = variance === 0;
  const methods = Object.entries(report.totals_by_method ?? {}) as [PaymentMethod, number][];

  return (
    <div className="flex flex-col gap-5" data-testid="z-report">
      <section>
        {/* Gross cash through the till. Not revenue, not the owner's income. Do not rename. */}
        <p className="text-sm uppercase tracking-wide text-[var(--ink-3)]">Money taken</p>
        <p data-testid="z-money-taken" className="num text-4xl font-bold">
          {formatPesewas(report.money_taken_pesewas ?? 0)}
        </p>
      </section>

      <section
        data-testid="z-variance"
        data-balanced={balanced}
        className={`rounded-xl border-2 p-4 ${
          balanced ? "border-[var(--accent-line)] bg-[var(--accent-soft)]" : "border-[var(--danger)]"
        }`}
      >
        <p className="text-sm uppercase tracking-wide text-[var(--ink-3)]">Variance</p>
        <p
          className={`num text-5xl font-bold ${balanced ? "text-[var(--accent)]" : "text-[var(--danger)]"}`}
        >
          {formatPesewas(variance)}
        </p>
        <p className="mt-1 text-lg">
          {balanced
            ? "The drawer balances."
            : variance < 0
              ? "The drawer is short."
              : "There is more in the drawer than the till expected."}
        </p>
      </section>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-lg">
        <Row label="Opening float" value={report.opening_float_pesewas} />
        <Row label="Cash payments" value={report.cash_payments_pesewas ?? 0} />
        <Row label="Paid out" value={report.paid_out_pesewas ?? 0} />
        <Row label="Paid in" value={report.paid_in_pesewas ?? 0} />
        <Row label="Expected in drawer" value={report.expected_cash_pesewas ?? 0} />
        <Row label="Counted" value={report.declared_cash_pesewas ?? 0} />
      </dl>

      {methods.length > 0 ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--ink-3)]">
            By method
          </h3>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-lg">
            {methods.map(([method, total]) => (
              <Row key={method} label={methodLabel(method)} value={total} />
            ))}
          </dl>
        </section>
      ) : null}

      {(report.movements ?? []).length > 0 ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--ink-3)]">
            Drawer movements
          </h3>
          <ul className="flex flex-col gap-2">
            {(report.movements ?? []).map((movement) => (
              <li
                key={movement.id}
                className="flex items-baseline justify-between rounded-lg bg-[var(--surface-2)] px-4 py-3"
              >
                <span>
                  {movement.kind.replaceAll("_", " ")} · {movement.reason_code.replaceAll("_", " ")}
                </span>
                <span className="num">{formatPesewas(movement.amount_pesewas)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <>
      <dt className="text-[var(--ink-2)]">{label}</dt>
      <dd className="num text-right">{formatPesewas(value)}</dd>
    </>
  );
}

type ZReportShape = Awaited<ReturnType<typeof fetchZReport>>;
