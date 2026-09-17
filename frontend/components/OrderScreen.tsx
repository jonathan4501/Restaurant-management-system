"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { v7 as uuidv7 } from "uuid";

import { ConnectivityBadge } from "@/components/ConnectivityBadge";
import { DraftPanel } from "@/components/DraftPanel";
import { MenuBrowser } from "@/components/MenuBrowser";
import { ModifierSheet } from "@/components/ModifierSheet";
import { TableGrid } from "@/components/TableGrid";
import { api } from "@/lib/api/client";
import { sortTables, type DraftModifier, type MenuItem, type MenuResponse, type TableRow } from "@/lib/domain";
import { useOrderMode } from "@/lib/hooks/useOrderMode";
import { useI18n } from "@/lib/i18n";
import { isQueued } from "@/lib/outbox";
import { useDraft } from "@/lib/stores/draft";
import { useStaff } from "@/lib/stores/staff";

function mapMenu(data: unknown): MenuResponse {
  const body = data as MenuResponse;
  return { categories: body.categories ?? [] };
}

function mapTables(data: unknown): TableRow[] {
  // The API returns a bare list; older mocks wrapped it in { tables }.
  const rows = Array.isArray(data) ? (data as TableRow[]) : ((data as { tables?: TableRow[] }).tables ?? []);
  return sortTables(rows);
}

export function OrderScreen() {
  const queryClient = useQueryClient();
  const { mode, canSeeTables, isGuestSurface } = useOrderMode();
  const staff = useStaff((s) => s.staff);
  const { t, locale, setLocale } = useI18n();
  const draft = useDraft();
  const [pickerItem, setPickerItem] = useState<MenuItem | null>(null);
  const [sent, setSent] = useState(false);

  const guest = mode === "qr" || mode === "guest";

  const menuQuery = useQuery({
    queryKey: ["menu", mode],
    queryFn: async () => {
      const { data, error } = guest ? await api.GET("/api/v1/guest/menu") : await api.GET("/api/v1/menu");
      if (error) throw error;
      return mapMenu(data);
    },
  });

  const tablesQuery = useQuery({
    queryKey: ["tables"],
    enabled: canSeeTables,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/tables");
      if (error) throw error;
      return mapTables(data);
    },
  });

  const openSession = useMutation({
    mutationFn: async (table: TableRow) => {
      if (table.open_session) {
        return { sessionId: table.open_session.id, tableId: table.id, tableNumber: table.number };
      }
      const sessionId = uuidv7();
      const { data, error } = await api.POST("/api/v1/sessions", {
        body: { id: sessionId, table_id: table.id, party_size: 2 },
      });
      if (error) throw error;
      const sid = (data as { id?: string }).id ?? sessionId;
      return { sessionId: sid, tableId: table.id, tableNumber: table.number };
    },
    onSuccess: ({ sessionId, tableId, tableNumber }) => {
      draft.setTable(tableId, tableNumber, sessionId);
      void queryClient.invalidateQueries({ queryKey: ["tables"] });
    },
  });

  const ensureOrder = useCallback(async (): Promise<{ orderId: string; queued: boolean }> => {
    if (draft.orderId) return { orderId: draft.orderId, queued: false };
    const orderId = uuidv7();
    const body = { id: orderId, session_id: draft.sessionId! };
    const { data, error, response } = guest
      ? await api.POST("/api/v1/guest/orders", { body })
      : await api.POST("/api/v1/orders", { body });
    if (error) throw error;
    const id = (data as unknown as { id?: string } | undefined)?.id ?? orderId;
    draft.setOrderId(id);
    return { orderId: id, queued: isQueued(response) };
  }, [draft, guest]);

  const sendMutation = useMutation({
    mutationFn: async () => {
      draft.setSubmitPending(true);
      let queued = false;
      const ensured = await ensureOrder();
      queued = queued || ensured.queued;
      const orderId = ensured.orderId;
      for (const line of draft.lines) {
        const request = {
          params: { path: { order_id: orderId } },
          body: {
            id: line.client_id,
            menu_item_id: line.menu_item_id,
            quantity: line.quantity,
            modifier_ids: line.modifiers.map((m) => m.id),
            notes: line.notes,
            course: 1,
          },
        };
        const { error, response } = guest
          ? await api.POST("/api/v1/guest/orders/{order_id}/items", request)
          : await api.POST("/api/v1/orders/{order_id}/items", request);
        if (error) throw error;
        queued = queued || isQueued(response);
      }
      const submit = { params: { path: { order_id: orderId } } };
      const { error: submitError, response: submitResponse } = guest
        ? await api.POST("/api/v1/guest/orders/{order_id}/submit", submit)
        : await api.POST("/api/v1/orders/{order_id}/submit", submit);
      if (submitError) throw submitError;
      queued = queued || isQueued(submitResponse);
      return { orderId, queued };
    },
    onSuccess: ({ queued }) => {
      draft.clearLines();
      draft.setSubmitPending(false);
      // Never claim the kitchen has the ticket while it is still on this device.
      if (!queued) setSent(true);
    },
    onError: () => {
      draft.setSubmitPending(false);
    },
  });

  function handleSelectTable(table: TableRow) {
    void openSession.mutate(table);
  }

  function handleAddLine(modifiers: DraftModifier[], quantity: number, notes: string) {
    if (!pickerItem) return;
    draft.addLine(pickerItem, modifiers, quantity, notes);
    setPickerItem(null);
  }

  const showTables = canSeeTables && !draft.tableId;
  const themeClass = isGuestSurface ? "guest-theme staff-shell" : "staff-theme staff-shell";

  return (
    <div className={themeClass} data-testid="order-screen" data-mode={mode}>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] px-4 py-3">
        <div>
          <p className="wordmark text-xl">RENZY</p>
          <h1 className="text-lg font-semibold">{isGuestSurface ? t("seeMenu") : "Order"}</h1>
        </div>
        <div className="flex items-center gap-3">
          {isGuestSurface ? (
            <button
              type="button"
              data-testid="locale-toggle"
              onClick={() => setLocale(locale === "en" ? "tw" : "en")}
              className="min-h-12 rounded-lg border border-[var(--line)] px-3 text-sm"
            >
              {t("language")}
            </button>
          ) : (
            <span className="text-sm text-[var(--ink-2)]">{staff?.name ?? "Staff"}</span>
          )}
          <ConnectivityBadge />
        </div>
      </header>

      {sent ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center" data-testid="order-sent">
          <p className="text-xl font-semibold">{t("yourOrderIsWithKitchen")}</p>
          <p className="text-sm text-[var(--ink-3)]">{t("billStaysOpen")}</p>
          <button
            type="button"
            data-testid="order-add-more"
            className="min-h-14 rounded-lg border border-[var(--line)] px-6"
            onClick={() => setSent(false)}
          >
            {t("addMore")}
          </button>
        </div>
      ) : (
        <div className="flex min-h-[calc(100vh-4rem)] flex-col lg:flex-row">
          <div className="flex min-h-0 flex-1 flex-col p-4">
            {showTables ? (
              <section>
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--ink-3)]">Tables</h2>
                {tablesQuery.isLoading ? <p className="text-sm">Loading tables…</p> : null}
                {tablesQuery.data ? (
                  <TableGrid tables={tablesQuery.data} selectedId={draft.tableId} onSelect={handleSelectTable} />
                ) : null}
              </section>
            ) : (
              <>
                {draft.tableNumber ? (
                  <div className="mb-3 flex items-center justify-between">
                    <p className="num text-lg font-semibold" data-testid="active-table">
                      Table {draft.tableNumber}
                    </p>
                    {canSeeTables ? (
                      <button type="button" className="min-h-14 text-sm text-[var(--accent)]" onClick={() => draft.reset()}>
                        Change table
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {menuQuery.isLoading ? <p className="text-sm">Loading menu…</p> : null}
                {menuQuery.data ? (
                  <MenuBrowser categories={menuQuery.data.categories} onSelectItem={setPickerItem} guestSurface={isGuestSurface} />
                ) : null}
              </>
            )}
          </div>
          {!showTables ? (
            <DraftPanel
              tableNumber={draft.tableNumber}
              lines={draft.lines}
              totalPesewas={draft.totalPesewas()}
              submitPending={draft.submitPending || sendMutation.isPending}
              onQuantityChange={draft.setQuantity}
              onSend={() => void sendMutation.mutate()}
              guestSurface={isGuestSurface}
            />
          ) : null}
        </div>
      )}

      <ModifierSheet
        item={pickerItem}
        open={pickerItem !== null}
        onClose={() => setPickerItem(null)}
        onAdd={handleAddLine}
        guestSurface={isGuestSurface}
      />
    </div>
  );
}
