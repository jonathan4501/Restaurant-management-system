import { create } from "zustand";
import { tokens } from "@/lib/auth/tokens";
import type { StaffRole, StaffSummary } from "@/lib/domain";

interface StaffState {
  token: string | null;
  staff: StaffSummary | null;
  hydrated: boolean;
  hydrate: () => void;
  setSession: (token: string, staff: StaffSummary) => void;
  clear: () => void;
  role: () => StaffRole | null;
}

export const useStaff = create<StaffState>((set, get) => ({
  token: null, staff: null, hydrated: false,
  hydrate: () => {
    const token = tokens.session();
    let staff: StaffSummary | null = null;
    try { const raw = typeof window !== "undefined" ? window.localStorage.getItem("renzy.staff") : null; if (raw) staff = JSON.parse(raw) as StaffSummary; } catch { /* */ }
    set({ token, staff, hydrated: true });
  },
  setSession: (token, staff) => {
    tokens.setSession(token);
    try { window.localStorage.setItem("renzy.staff", JSON.stringify(staff)); } catch { /* */ }
    set({ token, staff, hydrated: true });
  },
  clear: () => {
    tokens.setSession(null);
    try { window.localStorage.removeItem("renzy.staff"); } catch { /* */ }
    set({ token: null, staff: null, hydrated: true });
  },
  role: () => get().staff?.role ?? null,
}));
