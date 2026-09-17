"use client";

import { formatPesewas } from "@/lib/money";

import { ageMinutes, formatAge, stateLabel } from "../lib/till";
import type { BillState, OpenBill } from "../lib/types";

/** Chip colours match the meaning, not the workstream: amber is still cooking, teal is the cashier's. */
const CHIP_CLASS: Record<string, string> = {
  sent: "border-[var(--queue-line)] text-[var(--queue)]",
  cooking: "border-[var(--warn)] text-[var(--warn)]",
  food_ready: "border-[var(--warn)] text-[var(--warn)]",
  ready_to_pay: "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--accent)]",
  part_paid: "border-[var(--accent-line)] text-[var(--accent)]",
};

interface BillsListProps {
  bills: OpenBill[];
  outstandingPesewas: number;
  selectedSessionId: string | null;
  onSelect: (sessionId: string) => void;
  now: number;
  loading: boolean;
}

export function BillsList({
  bills,
  outstandingPesewas,
  selectedSessionId,
  onSelect,
  now,
  loading,
}: BillsListProps) {
  return (
    <section
      className="flex min-h-0 flex-col rounded-xl bg-[var(--surface-2)]"
      data-testid="bills-list"
    >
      <h2 className="flex items-baseline justify-between border-b border-[var(--line)] px-4 py-3">
        <span className="text-lg font-bold uppercase tracking-wide">Open bills</span>
        <span className="text-right">
          <span className="block text-xs uppercase tracking-wide text-[var(--ink-3)]">
            Still owing
          </span>
          <span data-testid="bills-outstanding" className="num text-lg font-bold">
            {formatPesewas(outstandingPesewas)}
          </span>
        </span>
      </h2>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3">
        {loading ? <p className="p-4 text-lg">Loading the board…</p> : null}
        {!loading && bills.length === 0 ? (
          <p className="px-2 py-8 text-center text-lg text-[var(--ink-3)]">
            Nothing owing. Every table is settled.
          </p>
        ) : null}

        {bills.map((bill) => {
          const selected = bill.session_id === selectedSessionId;
          return (
            <button
              key={bill.session_id}
              type="button"
              data-testid={`bill-${bill.table_number}`}
              data-payable={bill.payable}
              data-selected={selected}
              onClick={() => onSelect(bill.session_id)}
              className={`flex min-h-20 items-center gap-4 rounded-lg border px-4 py-3 text-left ${
                selected
                  ? "border-[var(--accent)] bg-[var(--surface-3)]"
                  : "border-[var(--line)] bg-[var(--surface)]"
              }`}
            >
              <span className="num w-14 shrink-0 text-3xl font-bold">{bill.table_number}</span>
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span
                  className={`w-fit rounded-full border px-3 py-0.5 text-sm font-semibold ${
                    CHIP_CLASS[bill.state ?? ""] ?? "border-[var(--line)] text-[var(--ink-3)]"
                  }`}
                >
                  {stateLabel(bill.state as BillState | null)}
                </span>
                <span className="text-sm text-[var(--ink-3)]">
                  {formatAge(ageMinutes(bill.opened_at, now))} · {bill.order_count}{" "}
                  {bill.order_count === 1 ? "round" : "rounds"}
                </span>
              </span>
              <span className="num shrink-0 text-right text-2xl font-bold">
                {formatPesewas(bill.balance_pesewas)}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
