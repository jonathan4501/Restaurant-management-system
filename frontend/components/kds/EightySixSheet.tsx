"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/lib/api/client";
import type { MenuCategory, MenuItem, MenuResponse } from "@/lib/domain";

interface EightySixSheetProps {
  open: boolean;
  onClose: () => void;
  onDone: (message: string) => void;
}

/** "We are out of tilapia" — one tap, and every ordering screen stops offering it. */
export function EightySixSheet({ open, onClose, onDone }: EightySixSheetProps) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");

  const menu = useQuery({
    queryKey: ["menu"],
    enabled: open,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/menu");
      if (error) throw error;
      return (data as unknown as MenuResponse).categories ?? [];
    },
  });

  const toggle = useMutation({
    mutationFn: async (item: MenuItem) => {
      const path = item.is_available
        ? "/api/v1/menu/items/{item_id}/86"
        : "/api/v1/menu/items/{item_id}/restore";
      const { error } = await api.POST(path as "/api/v1/menu/items/{item_id}/86", {
        params: { path: { item_id: item.id } },
      });
      if (error) throw error;
      return item;
    },
    onSuccess: (item) => {
      onDone(item.is_available ? `${item.name} is off the menu` : `${item.name} is back on`);
      void queryClient.invalidateQueries({ queryKey: ["menu"] });
      void queryClient.invalidateQueries({ queryKey: ["kds"] });
    },
  });

  if (!open) return null;

  const categories: MenuCategory[] = menu.data ?? [];
  const needle = filter.trim().toLowerCase();

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/70 p-4" role="dialog" aria-modal>
      <div className="flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
        <header className="flex items-center justify-between gap-4 border-b border-[var(--line)] p-4">
          <h2 className="text-2xl font-bold">What are we out of?</h2>
          <button
            type="button"
            data-testid="eighty-six-close"
            onClick={onClose}
            className="min-h-14 rounded-lg border border-[var(--line)] px-5 text-lg"
          >
            Close
          </button>
        </header>
        <div className="border-b border-[var(--line)] p-3">
          <input
            data-testid="eighty-six-filter"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Search the menu"
            className="min-h-14 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-4 text-lg"
          />
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {menu.isLoading ? <p className="p-4 text-lg">Loading menu…</p> : null}
          {categories.map((category) => {
            const items = category.items.filter((i) => i.name.toLowerCase().includes(needle));
            if (items.length === 0) return null;
            return (
              <section key={category.id} className="mb-4">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--ink-3)]">
                  {category.name}
                </h3>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      data-testid={`eighty-six-${item.id}`}
                      data-available={item.is_available}
                      disabled={toggle.isPending}
                      onClick={() => toggle.mutate(item)}
                      className={`flex min-h-16 items-center justify-between rounded-lg border px-4 text-left text-lg ${
                        item.is_available
                          ? "border-[var(--line)] bg-[var(--surface-2)]"
                          : "border-[var(--danger)] bg-[var(--surface-3)] text-[var(--ink-3)]"
                      }`}
                    >
                      <span className={item.is_available ? "" : "line-through"}>{item.name}</span>
                      <span className="text-sm font-semibold uppercase tracking-wide">
                        {item.is_available ? "86 it" : "Back on"}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
