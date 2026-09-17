"use client";

import { formatPesewas } from "@/lib/money";

import { MONEY_TAKEN } from "../lib/labels";
import type { Today, Variance } from "../lib/types";

interface Props {
  today: Today;
  voidValuePesewas: number;
}

export function TodayStrip({ today, voidValuePesewas }: Props) {
  const tiles = [
    {
      id: "money-taken",
      label: MONEY_TAKEN,
      value: formatPesewas(today.money_taken_pesewas),
      caption: "cash + mobile money + card",
    },
    {
      id: "covers",
      label: "Covers",
      value: String(today.covers),
      caption: `${today.bills_settled} bills settled`,
    },
    {
      id: "average-bill",
      label: "Average bill",
      value: formatPesewas(today.average_bill_pesewas),
      caption: "Money taken ÷ bills settled",
    },
    {
      id: "lost-voids",
      label: "Lost to voids",
      value: formatPesewas(voidValuePesewas),
      caption: "food cooked, never paid for",
    },
    {
      id: "open-bills",
      label: "Open bills",
      value: String(today.open_bills),
      caption: `${formatPesewas(today.open_balance_pesewas)} still owing`,
    },
  ];

  return (
    <section data-testid="today-strip" className="mb-8">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <h2 className="text-lg font-semibold">Today so far</h2>
        <p className="max-w-md text-right text-xs text-[var(--ink-3)]">
          {MONEY_TAKEN} is gross cash through the till — before tax, food cost, wages and rent.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-px border border-[var(--line)] bg-[var(--line)] sm:grid-cols-3 lg:grid-cols-5">
        {tiles.map((tile) => (
          <div key={tile.id} data-testid={`today-${tile.id}`} className="bg-[var(--surface)] p-3">
            <p className="text-xs uppercase tracking-wide text-[var(--ink-3)]">{tile.label}</p>
            <p className="num mt-1 text-xl font-semibold">{tile.value}</p>
            <p className="mt-1 text-xs text-[var(--ink-3)]">{tile.caption}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function voidValueFromVariance(v: Variance | undefined): number {
  return v?.void_value_pesewas ?? 0;
}
