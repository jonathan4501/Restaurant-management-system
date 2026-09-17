"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { formatPesewas } from "@/lib/money";
import { useEventStream } from "@/lib/realtime/useEventStream";
import { useStaff } from "@/lib/stores/staff";

import { BillPanel } from "./BillPanel";
import { BillsList } from "./BillsList";
import { CloseShiftSheet } from "./CloseShiftSheet";
import { DrawerSheet } from "./DrawerSheet";
import { OpenShiftScreen } from "./OpenShiftScreen";
import { PaySheet } from "./PaySheet";
import { fetchBill, fetchCurrentShift, fetchOpenBills } from "../lib/api";
import type { Shift } from "../lib/types";

export function TillScreen() {
  const queryClient = useQueryClient();
  const staff = useStaff((s) => s.staff);
  const hydrate = useStaff((s) => s.hydrate);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => hydrate(), [hydrate]);

  // Bill ages are read in whole minutes, so once a minute is often enough.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(id);
  }, [toast]);

  // SSE invalidates "shift", "bills" and "order" for us (lib/realtime/sse.ts::affectedQueries).
  const stream = useEventStream();

  const shift = useQuery({ queryKey: ["shift"], queryFn: fetchCurrentShift });

  const bills = useQuery({
    queryKey: ["bills"],
    queryFn: fetchOpenBills,
    enabled: Boolean(shift.data),
    refetchInterval: stream.state === "live" ? false : 15_000,
  });

  const bill = useQuery({
    queryKey: ["bills", selectedSessionId],
    queryFn: () => fetchBill(selectedSessionId as string),
    enabled: selectedSessionId !== null,
  });

  function refresh(message: string) {
    setToast(message);
    void queryClient.invalidateQueries({ queryKey: ["bills"] });
    void queryClient.invalidateQueries({ queryKey: ["shift"] });
  }

  if (shift.isLoading) {
    return (
      <main className="staff-shell staff-theme flex min-h-screen items-center justify-center">
        <p className="text-lg">Opening the till…</p>
      </main>
    );
  }

  if (!shift.data) {
    return (
      <OpenShiftScreen
        cashierName={staff?.name ?? "Cashier"}
        onOpened={(opened: Shift) => {
          // The shift comes back from the command, so the board appears without a round trip.
          queryClient.setQueryData(["shift"], opened);
          void queryClient.invalidateQueries({ queryKey: ["bills"] });
        }}
      />
    );
  }

  const openShiftData = shift.data;
  const selectedBill = selectedSessionId ? bill.data : undefined;

  return (
    <main
      className="staff-shell staff-theme flex h-screen flex-col overflow-hidden"
      data-testid="till"
    >
      {stream.stale ? (
        <div
          data-testid="till-offline"
          className="bg-[var(--danger)] px-4 py-3 text-center text-xl font-bold text-[#2a0d0b]"
        >
          OFFLINE — write payments down and enter them when this comes back
        </div>
      ) : null}

      <header className="flex items-center justify-between gap-4 border-b border-[var(--line)] px-4 py-3">
        <div>
          <h1 className="text-xl font-bold">Till</h1>
          <p className="text-sm text-[var(--ink-3)]">
            {staff?.name ?? "Cashier"} · float{" "}
            <span className="num">{formatPesewas(openShiftData.opening_float_pesewas)}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            data-testid="till-connection"
            data-state={stream.state}
            className="rounded-full border border-[var(--line)] px-3 py-1 text-sm text-[var(--ink-3)]"
          >
            {stream.state === "live" ? "Live" : stream.state === "polling" ? "Catching up" : stream.state}
          </span>
          <button
            type="button"
            data-testid="till-drawer"
            onClick={() => setDrawerOpen(true)}
            className="min-h-14 rounded-lg border border-[var(--line)] px-5 text-lg"
          >
            Drawer
          </button>
          <button
            type="button"
            data-testid="till-close-shift"
            onClick={() => setClosing(true)}
            className="min-h-14 rounded-lg border border-[var(--line)] px-5 text-lg"
          >
            Close shift
          </button>
        </div>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-2">
        <BillsList
          bills={bills.data?.bills ?? []}
          outstandingPesewas={bills.data?.outstanding_pesewas ?? 0}
          selectedSessionId={selectedSessionId}
          onSelect={setSelectedSessionId}
          now={now}
          loading={bills.isLoading}
        />
        <BillPanel
          bill={selectedBill}
          loading={selectedSessionId !== null && bill.isLoading}
          onPay={() => setPaying(true)}
          onChanged={refresh}
        />
      </div>

      {paying && selectedBill ? (
        <PaySheet
          sessionId={selectedBill.session_id}
          tableNumber={selectedBill.table_number}
          balancePesewas={selectedBill.balance_pesewas}
          onClose={() => setPaying(false)}
          onPaid={(result) => {
            refresh(
              result.settled
                ? "Paid in full"
                : `${formatPesewas(result.balance_pesewas)} still to pay`,
            );
            void queryClient.invalidateQueries({ queryKey: ["bills", selectedSessionId] });
            if (result.settled) setPaying(false);
          }}
        />
      ) : null}

      {drawerOpen ? (
        <DrawerSheet
          shiftId={openShiftData.id}
          onClose={() => setDrawerOpen(false)}
          onDone={refresh}
        />
      ) : null}

      {closing ? (
        <CloseShiftSheet
          shift={openShiftData}
          onClose={() => setClosing(false)}
          onClosed={() => {
            setClosing(false);
            queryClient.setQueryData(["shift"], null);
          }}
        />
      ) : null}

      {toast ? (
        <div
          data-testid="till-toast"
          role="status"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl bg-[var(--accent)] px-8 py-4 text-2xl font-bold text-[var(--accent-ink)]"
        >
          {toast}
        </div>
      ) : null}
    </main>
  );
}
