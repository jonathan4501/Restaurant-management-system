"use client";

import { useMemo, useState } from "react";

import { formatPesewas } from "@/lib/money";
import type { MenuCategory, MenuItem } from "@/lib/domain";

interface MenuBrowserProps {
  categories: MenuCategory[];
  onSelectItem: (item: MenuItem) => void;
  guestSurface?: boolean;
}

export function MenuBrowser({ categories, onSelectItem, guestSurface }: MenuBrowserProps) {
  const sorted = useMemo(
    () => [...categories].sort((a, b) => a.sort_order - b.sort_order).map((c) => ({ ...c, items: [...c.items].sort((x, y) => (x.sort_order ?? 0) - (y.sort_order ?? 0) || x.name.localeCompare(y.name)) })),
    [categories],
  );
  const [activeId, setActiveId] = useState(sorted[0]?.id ?? "");
  const active = sorted.find((c) => c.id === activeId) ?? sorted[0];

  return (
    <div className={`flex min-h-0 flex-1 flex-col ${guestSurface ? "text-[var(--guest-ink)]" : ""}`} data-testid="menu-browser">
      <div className="flex gap-2 overflow-x-auto pb-3" role="tablist">
        {sorted.map((cat) => (
          <button
            key={cat.id}
            type="button"
            role="tab"
            aria-selected={cat.id === active?.id}
            data-testid={`menu-tab-${cat.name.toLowerCase().replace(/\s+/g, "-")}`}
            onClick={() => setActiveId(cat.id)}
            className={`min-h-14 shrink-0 rounded-full px-4 text-sm font-semibold ${
              cat.id === active?.id
                ? "bg-[var(--accent)] text-[var(--accent-ink)]"
                : "border border-[var(--line)] bg-[var(--surface-2)] text-[var(--ink-2)]"
            }`}
          >
            {cat.name}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 overflow-y-auto sm:grid-cols-3" data-testid="menu-items">
        {active?.items.map((item) => {
          const unavailable = !item.is_available;
          return (
            <button
              key={item.id}
              type="button"
              data-testid={`menu-item-${item.id}`}
              data-available={item.is_available}
              disabled={unavailable}
              onClick={() => onSelectItem(item)}
              className={`flex min-h-28 flex-col items-start rounded-xl border p-3 text-left ${
                unavailable
                  ? "cursor-not-allowed border-[var(--line)] bg-[var(--surface-2)] opacity-50"
                  : "border-[var(--line)] bg-[var(--surface)] active:bg-[var(--surface-3)]"
              }`}
            >
              <span className="line-clamp-2 text-sm font-semibold">{item.name}</span>
              <span className="num mt-auto text-sm text-[var(--brass)]">{formatPesewas(item.price_pesewas)}</span>
              {unavailable ? <span className="text-xs font-semibold uppercase text-[var(--danger)]">86&apos;d</span> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
