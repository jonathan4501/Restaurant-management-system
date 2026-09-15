import { create } from "zustand";
import { v7 as uuidv7 } from "uuid";
import { draftTotalPesewas, type DraftLine, type DraftModifier, type MenuItem } from "@/lib/domain";

interface DraftState {
  tableId: string | null; tableNumber: string | null; sessionId: string | null; orderId: string | null;
  lines: DraftLine[]; submitPending: boolean;
  setTable: (tableId: string, tableNumber: string, sessionId: string | null) => void;
  setOrderId: (orderId: string) => void;
  addLine: (item: MenuItem, modifiers: DraftModifier[], quantity: number, notes: string) => void;
  setQuantity: (clientId: string, quantity: number) => void;
  clearLines: () => void; reset: () => void; setSubmitPending: (p: boolean) => void;
  totalPesewas: () => number;
}

const empty = { tableId: null as string | null, tableNumber: null as string | null, sessionId: null as string | null, orderId: null as string | null, lines: [] as DraftLine[], submitPending: false };

export const useDraft = create<DraftState>((set, get) => ({
  ...empty,
  setTable: (tableId, tableNumber, sessionId) => set({ tableId, tableNumber, sessionId, orderId: null, lines: [], submitPending: false }),
  setOrderId: (orderId) => set({ orderId }),
  addLine: (item, modifiers, quantity, notes) => set((s) => ({ lines: [...s.lines, { client_id: uuidv7(), menu_item_id: item.id, name_snapshot: item.name, unit_price_pesewas: item.price_pesewas, quantity, modifiers, notes }] })),
  setQuantity: (clientId, quantity) => {
    if (quantity < 1) { set((s) => ({ lines: s.lines.filter((l) => l.client_id !== clientId) })); return; }
    set((s) => ({ lines: s.lines.map((l) => (l.client_id === clientId ? { ...l, quantity } : l)) }));
  },
  clearLines: () => set({ lines: [] }),
  reset: () => set({ ...empty }),
  setSubmitPending: (submitPending) => set({ submitPending }),
  totalPesewas: () => draftTotalPesewas(get().lines),
}));
