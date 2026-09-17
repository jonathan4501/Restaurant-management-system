"use client";

import { useEffect, useState } from "react";

import { formatPesewas } from "@/lib/money";
import type { DraftModifier, MenuItem } from "@/lib/domain";
import {
  defaultSelections,
  requiredGroupsSatisfied,
  selectedModifiers,
  selectionExtraPesewas,
  toggleModifier,
  type ModifierSelections,
} from "@/lib/order/modifiers";
import { useI18n } from "@/lib/i18n";

interface ModifierSheetProps {
  item: MenuItem | null;
  open: boolean;
  onClose: () => void;
  onAdd: (modifiers: DraftModifier[], quantity: number, notes: string) => void;
  guestSurface?: boolean;
}

export function ModifierSheet({ item, open, onClose, onAdd, guestSurface }: ModifierSheetProps) {
  const { t } = useI18n();
  const [selections, setSelections] = useState<ModifierSelections>({});
  const [quantity, setQuantity] = useState(1);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (item) {
      setSelections(defaultSelections(item.modifier_groups));
      setQuantity(1);
      setNotes("");
    }
  }, [item]);

  if (!open || !item) return null;

  const extras = selectionExtraPesewas(item.modifier_groups, selections);
  const lineTotal = (item.price_pesewas + extras) * quantity;
  const canAdd = requiredGroupsSatisfied(item.modifier_groups, selections);

  function handleAdd() {
    if (!item || !canAdd) return;
    const mods = selectedModifiers(item.modifier_groups, selections).map((m) => ({
      id: m.id,
      name: m.name,
      price_pesewas: m.price_pesewas,
    }));
    onAdd(mods, quantity, notes);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-4 sm:items-center" role="dialog" aria-modal data-testid="modifier-sheet">
      <div className={`flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-[var(--line)] sm:rounded-2xl ${guestSurface ? "bg-[var(--guest-surface)] text-[var(--guest-ink)]" : "bg-[var(--surface)]"}`}>
        <div className="border-b border-[var(--line)] p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">{item.name}</h2>
              <p className="num text-sm text-[var(--brass)]">{formatPesewas(item.price_pesewas)}</p>
            </div>
            <button type="button" onClick={onClose} className="min-h-14 px-4 text-sm">
              {t("cancel")}
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {item.modifier_groups.map((group) => (
            <fieldset key={group.id} className="mb-4">
              <legend className="mb-2 text-sm font-semibold">
                {group.name}
                {group.is_required ? " *" : ""}
              </legend>
              <div className="flex flex-col gap-2">
                {group.modifiers.map((mod) => {
                  const checked = (selections[group.id] ?? []).includes(mod.id);
                  const inputType = group.selection === "ONE" ? "radio" : "checkbox";
                  return (
                    <label
                      key={mod.id}
                      data-testid={`modifier-${mod.id}`}
                      className={`flex min-h-14 cursor-pointer items-center justify-between rounded-lg border px-3 ${
                        checked ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--line)]"
                      }`}
                    >
                      <span className="flex items-center gap-3">
                        <input
                          type={inputType}
                          name={group.id}
                          checked={checked}
                          onChange={() => setSelections((prev) => toggleModifier(item.modifier_groups, prev, group.id, mod.id))}
                        />
                        {mod.name}
                      </span>
                      {mod.price_pesewas > 0 ? (
                        <span className="num text-sm">+{formatPesewas(mod.price_pesewas)}</span>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}
          <label className="mb-4 block text-sm">
            Notes
            <input
              data-testid="modifier-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="mt-1 w-full min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3"
              placeholder="No pepper, extra crispy…"
            />
          </label>
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Quantity</span>
            <div className="flex items-center gap-2">
              <button type="button" data-testid="modifier-qty-minus" className="min-h-14 min-w-14 rounded-lg border" onClick={() => setQuantity((q) => Math.max(1, q - 1))}>
                −
              </button>
              <span className="num min-w-8 text-center">{quantity}</span>
              <button type="button" data-testid="modifier-qty-plus" className="min-h-14 min-w-14 rounded-lg border" onClick={() => setQuantity((q) => q + 1)}>
                +
              </button>
            </div>
          </div>
        </div>
        <div className="border-t border-[var(--line)] p-4">
          <button
            type="button"
            data-testid="modifier-add"
            disabled={!canAdd}
            onClick={handleAdd}
            className="flex min-h-16 w-full items-center justify-between rounded-lg bg-[var(--accent)] px-4 text-lg font-semibold text-[var(--accent-ink)] disabled:opacity-40"
          >
            <span>{t("add")}</span>
            <span className="num">{formatPesewas(lineTotal)}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
