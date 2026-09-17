"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { AuthoriseSheet } from "@/components/AuthoriseSheet";
import { formatPesewas } from "@/lib/money";

import { DiscountSheet } from "./DiscountSheet";
import { problemMessage, reopenSession, voidOrder } from "../lib/api";
import { payBlockedReason } from "../lib/till";
import type { Bill, BillLine, BillOrder } from "../lib/types";

interface BillPanelProps {
  bill: Bill | undefined;
  loading: boolean;
  onPay: () => void;
  onChanged: (message: string) => void;
}

export function BillPanel({ bill, loading, onPay, onChanged }: BillPanelProps) {
  const [discountOrder, setDiscountOrder] = useState<BillOrder | null>(null);
  const [voidingOrder, setVoidingOrder] = useState<BillOrder | null>(null);
  const [reopening, setReopening] = useState(false);

  const kill = useMutation({
    mutationFn: ({
      order,
      token,
      reasonCode,
    }: {
      order: BillOrder;
      token: string;
      reasonCode: string;
    }) => voidOrder(order.id, { token, reason_code: reasonCode }),
    onSuccess: (_result, { order }) => onChanged(`${orderLabel(order)} voided`),
  });

  const reopen = useMutation({
    mutationFn: ({ token, reasonCode }: { token: string; reasonCode: string }) =>
      reopenSession(bill?.session_id ?? "", { token, reason_code: reasonCode }),
    onSuccess: () => onChanged("Bill reopened — the owner has been told"),
  });

  if (loading) {
    return <Frame><p className="p-6 text-lg">Loading the bill…</p></Frame>;
  }
  if (!bill) {
    return (
      <Frame>
        <p className="p-6 text-center text-lg text-[var(--ink-3)]">
          Pick a table on the left to see its bill.
        </p>
      </Frame>
    );
  }

  const blocked = payBlockedReason(bill);
  const settled = bill.balance_pesewas <= 0;
  const liveOrders = bill.orders.filter((order) => order.status !== "VOIDED");

  return (
    <Frame testId="bill-panel">
      <header className="flex items-baseline justify-between border-b border-[var(--line)] px-4 py-3">
        <h2 className="text-lg font-bold uppercase tracking-wide">Table {bill.table_number}</h2>
        <span className="text-sm text-[var(--ink-3)]">
          {liveOrders.length} {liveOrders.length === 1 ? "round" : "rounds"}
        </span>
      </header>

      <div className="flex-1 overflow-y-auto p-3">
        {liveOrders.map((order) => {
          const lines = bill.lines.filter((line) => line.order_id === order.id);
          const discount = bill.discounts.find((d) => d.order_id === order.id);
          return (
            <section
              key={order.id}
              data-testid={`bill-order-${order.id}`}
              className="mb-3 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] p-3"
            >
              <h3 className="mb-2 flex items-baseline justify-between text-sm uppercase tracking-wide text-[var(--ink-3)]">
                <span>{orderLabel(order)}</span>
                <span>{order.status.toLowerCase()}</span>
              </h3>

              <ul className="flex flex-col gap-2">
                {lines.map((line) => (
                  <LineRow key={line.item_id} line={line} />
                ))}
              </ul>

              {discount ? (
                <p className="mt-2 flex items-baseline justify-between text-[var(--accent)]">
                  <span>Discount</span>
                  <span className="num">−{formatPesewas(discount.discount_pesewas)}</span>
                </p>
              ) : null}

              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  data-testid={`discount-${order.id}`}
                  onClick={() => setDiscountOrder(order)}
                  className="min-h-14 flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-base"
                >
                  Discount
                </button>
                <button
                  type="button"
                  data-testid={`void-${order.id}`}
                  onClick={() => setVoidingOrder(order)}
                  className="min-h-14 flex-1 rounded-lg border border-[var(--danger)] px-3 text-base text-[var(--danger)]"
                >
                  Void round
                </button>
              </div>
            </section>
          );
        })}

        {kill.isError || reopen.isError ? (
          <p data-testid="bill-error" className="px-1 text-[var(--danger)]">
            {problemMessage(kill.error ?? reopen.error, "That did not go through.")}
          </p>
        ) : null}
      </div>

      <footer className="border-t border-[var(--line)] p-4">
        <dl className="mb-3 grid grid-cols-2 gap-y-1 text-lg">
          <dt className="text-[var(--ink-2)]">Bill total</dt>
          <dd data-testid="bill-total" className="num text-right">
            {formatPesewas(bill.bill_total_pesewas)}
          </dd>
          <dt className="text-[var(--ink-2)]">Paid so far</dt>
          <dd data-testid="bill-paid" className="num text-right">
            {formatPesewas(bill.paid_pesewas)}
          </dd>
          <dt className="text-xl font-bold">Balance</dt>
          <dd data-testid="bill-balance" className="num text-right text-xl font-bold">
            {formatPesewas(bill.balance_pesewas)}
          </dd>
        </dl>

        {blocked ? (
          <p data-testid="bill-blocked" className="mb-2 text-[var(--warn)]">
            {blocked}
          </p>
        ) : null}

        <button
          type="button"
          data-testid="bill-pay"
          disabled={blocked !== null}
          onClick={onPay}
          className="min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)] disabled:opacity-40"
        >
          Take payment
        </button>

        <div className="mt-2 flex gap-2">
          <button
            type="button"
            data-testid="bill-reopen"
            disabled={!settled}
            onClick={() => setReopening(true)}
            className="min-h-14 flex-1 rounded-lg border border-[var(--line)] px-3 text-base disabled:opacity-40"
          >
            Reopen bill
          </button>
          {/* The print bridge and its PRINT_RECEIPT command land with WS12; there is nothing to call yet. */}
          <button
            type="button"
            data-testid="bill-reprint"
            disabled
            className="min-h-14 flex-1 rounded-lg border border-[var(--line)] px-3 text-base disabled:opacity-40"
          >
            Reprint receipt
            <span className="block text-xs text-[var(--ink-3)]">Needs the print bridge</span>
          </button>
        </div>
      </footer>

      {discountOrder ? (
        <DiscountSheet
          orderId={discountOrder.id}
          orderLabel={orderLabel(discountOrder)}
          orderTotalPesewas={discountOrder.total_pesewas}
          onClose={() => setDiscountOrder(null)}
          onDone={onChanged}
        />
      ) : null}

      {/* Everything on a cashier's screen has already reached the kitchen, so a void always needs a PIN. */}
      <AuthoriseSheet
        purpose="VOID_AFTER_ACK"
        open={voidingOrder !== null}
        onClose={() => setVoidingOrder(null)}
        onAuthorised={(token, reasonCode) => {
          if (voidingOrder) kill.mutate({ order: voidingOrder, token, reasonCode });
        }}
      />

      <AuthoriseSheet
        purpose="REOPEN"
        open={reopening}
        onClose={() => setReopening(false)}
        onAuthorised={(token, reasonCode) => reopen.mutate({ token, reasonCode })}
      />
    </Frame>
  );
}

function LineRow({ line }: { line: BillLine }) {
  return (
    <li className="flex items-start justify-between gap-3">
      <span className="min-w-0">
        <span className="num mr-2 text-[var(--ink-3)]">{line.quantity}×</span>
        {/* The snapshot taken when it was ordered. Never the menu's price today. */}
        <span>{line.name}</span>
        {line.modifiers.length > 0 ? (
          <span className="block text-sm text-[var(--ink-3)]">
            {line.modifiers.map((m) => m.name).join(", ")}
          </span>
        ) : null}
        {line.notes ? (
          <span className="block text-sm text-[var(--warn)]">{line.notes}</span>
        ) : null}
      </span>
      <span className="num shrink-0">{formatPesewas(line.line_total_pesewas)}</span>
    </li>
  );
}

function orderLabel(order: BillOrder): string {
  return order.order_number ? `Round #${order.order_number}` : "Round";
}

function Frame({ children, testId }: { children: React.ReactNode; testId?: string }) {
  return (
    <section
      data-testid={testId}
      className="flex min-h-0 flex-col rounded-xl bg-[var(--surface-2)]"
    >
      {children}
    </section>
  );
}
