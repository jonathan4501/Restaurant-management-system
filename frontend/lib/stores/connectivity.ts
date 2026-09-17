import { create } from "zustand";

export type ConnectivityStatus = "online" | "offline" | "pending";

interface ConnectivityState {
  status: ConnectivityStatus;
  pendingCount: number;
  failedCount: number;
  setOnline: (online: boolean) => void;
  setPendingCount: (n: number) => void;
  setFailedCount: (n: number) => void;
}

function deriveStatus(online: boolean, pending: number, failed: number): ConnectivityStatus {
  if (!online) return "offline";
  if (pending > 0 || failed > 0) return "pending";
  return "online";
}

function browserOnline(): boolean {
  return typeof navigator === "undefined" ? true : navigator.onLine;
}

export const useConnectivity = create<ConnectivityState>((set, get) => ({
  status: "online",
  pendingCount: 0,
  failedCount: 0,
  setOnline: (online) => {
    const { pendingCount, failedCount } = get();
    set({ status: deriveStatus(online, pendingCount, failedCount) });
  },
  setPendingCount: (pendingCount) => {
    const { failedCount } = get();
    set({ pendingCount, status: deriveStatus(browserOnline(), pendingCount, failedCount) });
  },
  setFailedCount: (failedCount) => {
    const { pendingCount } = get();
    set({ failedCount, status: deriveStatus(browserOnline(), pendingCount, failedCount) });
  },
}));
