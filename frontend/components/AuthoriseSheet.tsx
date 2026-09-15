"use client";

import { useState } from "react";

import { PinPad } from "@/components/PinPad";
import { api, isProblem } from "@/lib/api/client";
import type { AuthPurpose } from "@/lib/domain";

const REASON_CODES: Record<AuthPurpose, string[]> = {
  VOID_AFTER_ACK: ["GUEST_CHANGED_MIND", "WRONG_TABLE", "KITCHEN_ERROR", "OTHER"],
  DISCOUNT: ["STAFF_MEAL", "COMPLAINT", "PROMOTION", "OTHER"],
  COMP: ["OWNER_GUEST", "COMPLAINT", "OTHER"],
  PRICE_OVERRIDE: ["MENU_ERROR", "NEGOTIATED", "OTHER"],
  REOPEN: ["ADD_ITEMS", "WRONG_PAYMENT", "OTHER"],
  DRAWER_MOVEMENT: ["NO_SALE", "SUPPLIER_PAID", "CHANGE_FLOAT", "OTHER"],
  PAYMENT_VOID: ["WRONG_AMOUNT", "WRONG_METHOD", "DUPLICATE", "OTHER"],
  PRICE_CHANGE_IN_SERVICE: ["MENU_ERROR", "OTHER"],
  GUEST_EXIT: ["OTHER"],
};

interface AuthoriseSheetProps {
  purpose: AuthPurpose;
  open: boolean;
  onClose: () => void;
  onAuthorised: (token: string, reasonCode: string) => void;
}

export function AuthoriseSheet({ purpose, open, onClose, onAuthorised }: AuthoriseSheetProps) {
  const [pin, setPin] = useState("");
  const [reason, setReason] = useState(REASON_CODES[purpose][0] ?? "OTHER");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  async function submit() {
    setBusy(true);
    setError(null);
    const { data, error: reqError } = await api.POST("/api/v1/auth/authorise", { body: { pin, purpose } });
    setBusy(false);
    if (reqError) {
      const problem = reqError as unknown;
      setError(isProblem(problem) ? problem.detail || problem.title : "Authorisation failed");
      return;
    }
    const token = (data as { authorisation_token?: string } | undefined)?.authorisation_token;
    if (!token) {
      setError("Authorisation failed");
      return;
    }
    onAuthorised(token, reason);
    setPin("");
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 sm:items-center" role="dialog" aria-modal>
      <div className="w-full max-w-md rounded-t-2xl border border-[var(--line)] bg-[var(--surface)] p-4 sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Manager authorisation</h2>
          <button type="button" onClick={onClose} className="min-h-11 px-3 text-sm text-[var(--ink-3)]">
            Cancel
          </button>
        </div>
        <label className="mb-2 block text-sm text-[var(--ink-2)]">
          Reason
          <select
            data-testid="authorise-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 w-full min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3"
          >
            {REASON_CODES[purpose].map((code) => (
              <option key={code} value={code}>
                {code.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <PinPad value={pin} onChange={setPin} onSubmit={submit} disabled={busy} error={error} />
      </div>
    </div>
  );
}
