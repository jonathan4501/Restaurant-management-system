import { create } from "zustand";
import { tokens } from "@/lib/auth/tokens";
import type { StaffRole } from "@/lib/domain";

interface DeviceState {
  deviceToken: string | null;
  deviceId: string | null;
  label: string | null;
  allowedRoles: StaffRole[];
  hydrated: boolean;
  hydrate: () => void;
  setEnrolment: (p: { deviceToken: string; deviceId: string; label?: string | null; allowedRoles: StaffRole[] }) => void;
  clear: () => void;
}

export const useDevice = create<DeviceState>((set) => ({
  deviceToken: null, deviceId: null, label: null, allowedRoles: [], hydrated: false,
  hydrate: () => {
    const deviceToken = tokens.device();
    let meta = { deviceId: null as string | null, label: null as string | null, allowedRoles: [] as StaffRole[] };
    try { const raw = typeof window !== "undefined" ? window.localStorage.getItem("renzy.device_meta") : null; if (raw) meta = JSON.parse(raw) as typeof meta; } catch { /* */ }
    set({ deviceToken, deviceId: meta.deviceId, label: meta.label, allowedRoles: meta.allowedRoles ?? [], hydrated: true });
  },
  setEnrolment: ({ deviceToken, deviceId, label, allowedRoles }) => {
    tokens.setDevice(deviceToken);
    try { window.localStorage.setItem("renzy.device_meta", JSON.stringify({ deviceId, label: label ?? null, allowedRoles })); } catch { /* */ }
    set({ deviceToken, deviceId, label: label ?? null, allowedRoles, hydrated: true });
  },
  clear: () => {
    tokens.setDevice(null);
    try { window.localStorage.removeItem("renzy.device_meta"); } catch { /* */ }
    set({ deviceToken: null, deviceId: null, label: null, allowedRoles: [], hydrated: true });
  },
}));
