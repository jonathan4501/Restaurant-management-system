import type { Modifier, ModifierGroup } from "@/lib/domain";
export type ModifierSelections = Record<string, string[]>;

export function defaultSelections(groups: ModifierGroup[]): ModifierSelections {
  const next: ModifierSelections = {};
  for (const group of groups) {
    if (group.selection === "ONE") {
      const def = group.modifiers.find((m) => m.is_default && m.is_available) ?? group.modifiers.find((m) => m.is_available);
      next[group.id] = def ? [def.id] : [];
    } else {
      next[group.id] = group.modifiers.filter((m) => m.is_default && m.is_available).map((m) => m.id);
    }
  }
  return next;
}

export function toggleModifier(groups: ModifierGroup[], selections: ModifierSelections, groupId: string, modifierId: string): ModifierSelections {
  const group = groups.find((g) => g.id === groupId);
  if (!group) return selections;
  const current = selections[groupId] ?? [];
  if (group.selection === "ONE") return { ...selections, [groupId]: [modifierId] };
  const has = current.includes(modifierId);
  return { ...selections, [groupId]: has ? current.filter((id) => id !== modifierId) : [...current, modifierId] };
}

export function requiredGroupsSatisfied(groups: ModifierGroup[], selections: ModifierSelections): boolean {
  return groups.filter((g) => g.is_required).every((g) => (selections[g.id] ?? []).length > 0);
}

export function selectedModifiers(groups: ModifierGroup[], selections: ModifierSelections): Modifier[] {
  const out: Modifier[] = [];
  for (const group of groups) {
    const ids = new Set(selections[group.id] ?? []);
    for (const mod of group.modifiers) if (ids.has(mod.id)) out.push(mod);
  }
  return out;
}

export function selectionExtraPesewas(groups: ModifierGroup[], selections: ModifierSelections): number {
  return selectedModifiers(groups, selections).reduce((sum, m) => sum + m.price_pesewas, 0);
}

export function canAccessTables(mode: "waiter" | "guest" | "qr"): boolean {
  return mode === "waiter";
}
