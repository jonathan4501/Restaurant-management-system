"use client";

import { formatPesewas } from "@/lib/money";

import { isCashShort, sortShiftsByVariance, varianceHeadlines } from "../lib/aggregations";
import { formatClock } from "../lib/dates";
import type { LogPreset, Variance } from "../lib/types";

interface Props {
  variance: Variance;
  onOpenLog: (preset: LogPreset) => void;
  onOpenZReport: (shiftId: string) => void;
}

function Tile({
  label,
  value,
  detail,
  late,
  onClick,
  testId,
}: {
  label: string;
  value: string;
  detail: string;
  late: boolean;
  onClick: () => void;
  testId: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={`flex min-h-16 flex-col gap-1 border border-[var(--line)] p-3 text-left ${
        late ? "bg-[color-mix(in_srgb,var(--danger)_18%,var(--surface))]" : "bg-[var(--surface)]"
      }`}
    >
      <span className="flex items-center gap-2 text-xs uppercase tracking-wide text-[var(--ink-3)]">
        <span
          className={`inline-block h-2 w-2 shrink-0 ${late ? "bg-[var(--danger)]" : "bg-[var(--accent)]"}`}
          aria-hidden
        />
        {label}
      </span>
      <span className={`num text-xl font-semibold ${late ? "text-[var(--danger)]" : ""}`}>{value}</span>
      <span className="text-xs text-[var(--ink-2)]">{detail}</span>
    </button>
  );
}

export function VariancePanel({ variance, onOpenLog, onOpenZReport }: Props) {
  const h = varianceHeadlines(variance);
  const shifts = sortShiftsByVariance(variance.cash_variance_by_shift);
  const worst = shifts[0];
  const cashLate = isCashShort(h.cashVariancePesewas) || h.shortShiftCount > 0;
  const voidLate = h.voidCount > 0;
  const discountLate = h.discountCompPesewas > 0;
  const reopenLate = h.reopenedCount > 0;

  const cashDetail = worst
    ? `${worst.cashier} · counted ${
        worst.declared_cash_pesewas != null ? formatPesewas(worst.declared_cash_pesewas) : "—"
      } vs ${
        worst.expected_cash_pesewas != null ? formatPesewas(worst.expected_cash_pesewas) : "—"
      } expected`
    : "No closed shifts in this window";

  const voidSample = variance.voids_after_acknowledgement[0];
  const voidDetail = voidSample
    ? `${formatPesewas(h.voidValuePesewas)} · authorised by ${voidSample.authorised_by ?? "—"}`
    : "None in this window";

  const reopenSample = variance.reopened_bills[0];
  const reopenDetail = reopenSample
    ? `#${reopenSample.table_number ?? "—"} · ${reopenSample.reason_code ?? reopenSample.trigger} · ${formatClock(reopenSample.at)}`
    : "None in this window";

  return (
    <section data-testid="variance-panel" className="mb-8">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <h2 className="text-lg font-semibold">Where money can leak</h2>
        <p className="text-xs text-[var(--ink-3)]">Everything here needed a manager PIN and left a name.</p>
      </div>
      <div className="grid grid-cols-1 border border-[var(--line)] sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          testId="leak-cash"
          label="Cash variance"
          value={formatPesewas(h.cashVariancePesewas)}
          detail={cashDetail}
          late={cashLate}
          onClick={() => onOpenLog({ kind: "cash", shift_id: worst?.shift_id })}
        />
        <Tile
          testId="leak-voids"
          label="Voids after cooking started"
          value={String(h.voidCount)}
          detail={voidDetail}
          late={voidLate}
          onClick={() => onOpenLog({ kind: "voids" })}
        />
        <Tile
          testId="leak-discounts"
          label="Discounts & comps"
          value={formatPesewas(h.discountCompPesewas)}
          detail={`${h.discountStaffCount} staff · ${formatPesewas(variance.discount_pesewas)} off · ${formatPesewas(variance.comp_pesewas)} comps`}
          late={discountLate}
          onClick={() => onOpenLog({ kind: "discounts" })}
        />
        <Tile
          testId="leak-reopens"
          label="Bills reopened after closing"
          value={String(h.reopenedCount)}
          detail={reopenDetail}
          late={reopenLate}
          onClick={() => onOpenLog({ kind: "reopens" })}
        />
      </div>

      {h.gapCount > 0 ? (
        <button
          type="button"
          data-testid="leak-gaps"
          onClick={() => onOpenLog({ kind: "gaps" })}
          className="mt-2 flex min-h-14 w-full items-center justify-between border border-[var(--line)] bg-[color-mix(in_srgb,var(--danger)_12%,var(--surface))] px-3 text-left text-sm"
        >
          <span>Order-number gaps</span>
          <span className="num text-[var(--danger)]">{h.gapCount} missing</span>
        </button>
      ) : null}

      {shifts.length > 0 ? (
        <div className="mt-4 overflow-x-auto">
          <p className="mb-2 text-xs uppercase tracking-wide text-[var(--ink-3)]">Cash by shift</p>
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead className="text-xs uppercase text-[var(--ink-3)]">
              <tr>
                <th className="py-2 pr-3 font-medium">Cashier</th>
                <th className="py-2 pr-3 font-medium">Expected</th>
                <th className="py-2 pr-3 font-medium">Declared</th>
                <th className="py-2 pr-3 font-medium">Variance</th>
                <th className="py-2 font-medium">Z-report</th>
              </tr>
            </thead>
            <tbody>
              {shifts.map((s) => {
                const late = isCashShort(s.variance_pesewas);
                return (
                  <tr key={s.shift_id} className="border-t border-[var(--line)]">
                    <td className="py-3 pr-3">{s.cashier}</td>
                    <td className="num py-3 pr-3">
                      {s.expected_cash_pesewas != null ? formatPesewas(s.expected_cash_pesewas) : "—"}
                    </td>
                    <td className="num py-3 pr-3">
                      {s.declared_cash_pesewas != null ? formatPesewas(s.declared_cash_pesewas) : "—"}
                    </td>
                    <td className={`num py-3 pr-3 ${late ? "text-[var(--danger)]" : ""}`}>
                      {s.variance_pesewas != null ? formatPesewas(s.variance_pesewas) : "—"}
                    </td>
                    <td className="py-3">
                      <button
                        type="button"
                        data-testid={`z-report-${s.shift_id}`}
                        className="min-h-14 rounded-lg border border-[var(--line)] px-3 text-xs"
                        onClick={() => onOpenZReport(s.shift_id)}
                      >
                        Open Z-report
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
