"use client";

import { useQuery } from "@tanstack/react-query";

import { formatPesewas } from "@/lib/money";

import { fetchZReport, problemMessage } from "../lib/api";
import { MONEY_TAKEN, paymentMethodLabel } from "../lib/labels";

interface Props {
  shiftId: string;
  onClose: () => void;
}

export function ZReportSheet({ shiftId, onClose }: Props) {
  const report = useQuery({
    queryKey: ["z-report", shiftId],
    queryFn: () => fetchZReport(shiftId),
  });

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      data-testid="z-report-sheet"
    >
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Z-report</h2>
            <p className="text-xs text-[var(--ink-3)]">Shift {shiftId.slice(0, 8)}…</p>
          </div>
          <button
            type="button"
            data-testid="z-report-close"
            onClick={onClose}
            className="min-h-14 rounded-lg border border-[var(--line)] px-4 text-sm"
          >
            Close
          </button>
        </div>

        {report.isLoading ? <p className="text-sm text-[var(--ink-3)]">Loading…</p> : null}
        {report.isError ? (
          <p role="alert" className="text-sm text-[var(--danger)]">
            {problemMessage(report.error, "Could not load Z-report")}
          </p>
        ) : null}

        {report.data ? (
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt>{MONEY_TAKEN}</dt>
              <dd className="num font-semibold">
                {formatPesewas(report.data.money_taken_pesewas ?? 0)}
              </dd>
            </div>
            {report.data.by_method
              ? Object.entries(report.data.by_method).map(([method, amount]) => (
                  <div key={method} className="flex justify-between text-[var(--ink-2)]">
                    <dt>{paymentMethodLabel(method)}</dt>
                    <dd className="num">{formatPesewas(amount)}</dd>
                  </div>
                ))
              : null}
            <div className="flex justify-between border-t border-[var(--line)] pt-3">
              <dt>Expected cash</dt>
              <dd className="num">
                {report.data.expected_cash_pesewas != null
                  ? formatPesewas(report.data.expected_cash_pesewas)
                  : "—"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>Declared cash</dt>
              <dd className="num">
                {report.data.declared_cash_pesewas != null
                  ? formatPesewas(report.data.declared_cash_pesewas)
                  : "—"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>Variance</dt>
              <dd
                className={`num ${
                  (report.data.variance_pesewas ?? 0) < 0 ? "text-[var(--danger)]" : ""
                }`}
              >
                {report.data.variance_pesewas != null
                  ? formatPesewas(report.data.variance_pesewas)
                  : "—"}
              </dd>
            </div>
          </dl>
        ) : null}
      </div>
    </div>
  );
}
