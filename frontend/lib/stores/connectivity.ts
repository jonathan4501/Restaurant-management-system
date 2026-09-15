import { create } from "zustand";
export type ConnectivityStatus = "online" | "offline" | "pending";
interface ConnectivityState { status: ConnectivityStatus; pendingCount: number; setOnline: (online: boolean) => void; setPendingCount: (n: number) => void; }
export const useConnectivity = create<ConnectivityState>((set, get) => ({
  status: "online", pendingCount: 0,
  setOnline: (online) => { const pending = get().pendingCount; set({ status: !online ? "offline" : pending > 0 ? "pending" : "online" }); },
  setPendingCount: (pendingCount) => { const online = typeof navigator === "undefined" ? true : navigator.onLine; set({ pendingCount, status: !online ? "offline" : pendingCount > 0 ? "pending" : "online" }); },
}));
