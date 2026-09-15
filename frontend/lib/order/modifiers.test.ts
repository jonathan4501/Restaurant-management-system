import { describe, expect, it } from "vitest";
import { draftTotalPesewas, lineTotalPesewas, type DraftLine, type ModifierGroup } from "@/lib/domain";
import { canAccessTables, defaultSelections, requiredGroupsSatisfied, selectedModifiers, selectionExtraPesewas, toggleModifier, type ModifierSelections } from "@/lib/order/modifiers";

const groups: ModifierGroup[] = [
  { id: "g-pepper", name: "Pepper", selection: "ONE", is_required: true, sort_order: 0, modifiers: [
    { id: "mild", name: "Mild", price_pesewas: 0, is_default: true, is_available: true, sort_order: 0 },
    { id: "hot", name: "Hot", price_pesewas: 0, is_default: false, is_available: true, sort_order: 1 },
  ]},
  { id: "g-extras", name: "Extras", selection: "MANY", is_required: false, sort_order: 1, modifiers: [
    { id: "plantain", name: "Extra plantain", price_pesewas: 800, is_default: false, is_available: true, sort_order: 0 },
    { id: "shito", name: "Extra shito", price_pesewas: 500, is_default: false, is_available: true, sort_order: 1 },
  ]},
];

describe("draft line totals", () => {
  it("keeps integer pesewas", () => {
    const lines: DraftLine[] = [
      { client_id: "1", menu_item_id: "j", name_snapshot: "Jollof", unit_price_pesewas: 7500, quantity: 1, modifiers: [{ id: "p", name: "Extra plantain", price_pesewas: 800 }], notes: "" },
      { client_id: "2", menu_item_id: "c", name_snapshot: "Club Beer", unit_price_pesewas: 2500, quantity: 2, modifiers: [], notes: "" },
    ];
    expect(lineTotalPesewas(lines[0]!)).toBe(8300);
    expect(lineTotalPesewas(lines[1]!)).toBe(5000);
    expect(draftTotalPesewas(lines)).toBe(13300);
  });
});

describe("modifier rules", () => {
  it("defaults and enforces required ONE", () => {
    const sel = defaultSelections(groups);
    expect(sel["g-pepper"]).toEqual(["mild"]);
    expect(requiredGroupsSatisfied(groups, sel)).toBe(true);
    expect(requiredGroupsSatisfied(groups, { "g-pepper": [], "g-extras": [] } as ModifierSelections)).toBe(false);
  });
  it("ONE replaces MANY toggles", () => {
    let sel = defaultSelections(groups);
    sel = toggleModifier(groups, sel, "g-pepper", "hot");
    sel = toggleModifier(groups, sel, "g-extras", "plantain");
    sel = toggleModifier(groups, sel, "g-extras", "shito");
    expect(selectedModifiers(groups, sel).map((m) => m.id).sort()).toEqual(["hot", "plantain", "shito"]);
    expect(selectionExtraPesewas(groups, sel)).toBe(1300);
  });
});

describe("mode gating", () => {
  it("guest and qr cannot see tables", () => {
    expect(canAccessTables("waiter")).toBe(true);
    expect(canAccessTables("guest")).toBe(false);
    expect(canAccessTables("qr")).toBe(false);
  });
});
