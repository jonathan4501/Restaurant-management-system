"use client";

import { formatPesewas } from "@/lib/money";
import { lineTotalPesewas, type DraftLine } from "@/lib/domain";
import { useI18n } from "@/lib/i18n";
import { useConnectivity } from "@/lib/stores/connectivity";

interface DraftPanelProps {
  tableNumber: string | null;
  lines: DraftLine[];
  totalPesewas: number;
  submitPending: boolean;
  onQuantityChange: (clientId: string, quantity: number) => void;
  onSend: () => void;
  guestSurface?: boolean;
}

export function DraftPanel({
  tableNumber,
  lines,
  totalPesewas,
  submitPending,
  onQuantityChange,
  onSend,
  guestSurface,
}: DraftPanelProps) {
  const { t } = useI18n();
  const pendingCount = useConnectivity((s) => s.pendingCount);

  return (
    <aside
      className={`flex w-full flex-col border-t border-[var(--line)] lg:w-80 lg:border-l lg:border-t-0 ${guestSurface ? "bg-[var(--guest-surface-2)]" : "bg-[var(--surface-2)]"}`}
      data-testid="draft-panel"
    >
      <div className="border-b border-[var(--line)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--ink-3)]">{t("order")}</h2>
        {tableNumber ? <p className="num text-lg font-semibold">Table {tableNumber}</p> : null}
      </div>
      <ul className="flex-1 overflow-y-auto p-4">
        {lines.length === 0 ? (
          <li className="text-sm text-[var(--ink-3)]">Tap a menu item to start.</li>
        ) : (
          lines.map((line) => (
            <li key={line.client_id} className="mb-3 rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3" data-testid={`draft-line-${line.client_id}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold">{line.name_snapshot}</p>
                  {line.modifiers.length > 0 ? (
                    <p className="text-xs text-[var(--ink-3)]">{line.modifiers.map((m) => m.name).join(", ")}</p>
                  ) : null}
                  {line.notes ? <p className="text-xs italic text-[var(--ink-3)]">{line.notes}</p> : null}
                </div>
                <span className="num text-sm font-semibold text-[var(--brass)]">{formatPesewas(lineTotalPesewas(line))}</span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <button type="button" className="min-h-14 min-w-14 rounded border" onClick={() => onQuantityChange(line.client_id, line.quantity - 1)}>
                  −
                </button>
                <span className="num min-w-6 text-center">{line.quantity}</span>
                <button type="button" className="min-h-14 min-w-14 rounded border" onClick={() => onQuantityChange(line.client_id, line.quantity + 1)}>
                  +
                </button>
              </div>
            </li>
          ))
        )}
      </ul>
      <div className="border-t border-[var(--line)] p-4">
        <div className="mb-3 flex items-center justify-between text-sm">
          <span>{t("total")}</span>
          <span className="num text-lg font-semibold" data-testid="draft-total">
            {formatPesewas(totalPesewas)}
          </span>
        </div>
        <button
          type="button"
          data-testid="send-to-kitchen"
          disabled={lines.length === 0 || submitPending}
          onClick={onSend}
          className="flex min-h-16 w-full items-center justify-center rounded-lg bg-[var(--accent)] text-lg font-semibold text-[var(--accent-ink)] disabled:opacity-40"
        >
          {submitPending
            ? pendingCount > 0
              ? `Sending… (queued: ${pendingCount})`
              : "Sending…"
            : pendingCount > 0
              ? `Sending… (queued: ${pendingCount})`
              : t("sendToKitchen")}
        </button>
      </div>
    </aside>
  );
}
