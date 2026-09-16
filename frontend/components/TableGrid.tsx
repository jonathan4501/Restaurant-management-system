"use client";

import { tableChip, type TableRow, type TableStateChip } from "@/lib/domain";

const CHIP_LABEL: Record<TableStateChip, string> = {
  free: "Free",
  seated: "Seated",
  sent: "Sent",
  cooking: "Cooking",
  food_ready: "Food ready",
  ready_to_pay: "Bill",
  part_paid: "Part paid",
};

const CHIP_CLASS: Record<TableStateChip, string> = {
  free: "border-[var(--line)] text-[var(--ink-2)]",
  seated: "border-[var(--queue-line)] text-[var(--queue)]",
  sent: "border-[var(--warn-line)] text-[var(--warn)]",
  cooking: "border-[var(--warn-line)] text-[var(--warn)]",
  food_ready: "border-[var(--accent-line)] text-[var(--accent)]",
  ready_to_pay: "border-[var(--danger-line)] text-[var(--danger)]",
  part_paid: "border-[var(--danger-line)] text-[var(--danger)]",
};

interface TableGridProps {
  tables: TableRow[];
  selectedId: string | null;
  onSelect: (table: TableRow) => void;
}

export function TableGrid({ tables, selectedId, onSelect }: TableGridProps) {
  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6" data-testid="table-grid">
      {tables.map((table) => {
        const chip = tableChip(table);
        return (
        <button
          key={table.id}
          type="button"
          data-testid={`table-${table.number}`}
          data-state={chip}
          onClick={() => onSelect(table)}
          className={`flex min-h-20 flex-col items-center justify-center gap-1 rounded-xl border-2 bg-[var(--surface)] p-3 active:bg-[var(--surface-3)] ${
            selectedId === table.id ? "border-[var(--accent)] ring-2 ring-[var(--accent-soft)]" : "border-[var(--line)]"
          }`}
        >
          <span className="num text-2xl font-semibold">{table.number}</span>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${CHIP_CLASS[chip]}`}>
            {CHIP_LABEL[chip]}
          </span>
        </button>
        );
      })}
    </div>
  );
}
