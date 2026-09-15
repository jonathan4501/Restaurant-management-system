"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { tokens } from "@/lib/auth/tokens";
import type { QrEntryResponse } from "@/lib/domain";
import { useDraft } from "@/lib/stores/draft";

export default function GuestQrPage() {
  const params = useParams<{ qr_token: string }>();
  const router = useRouter();
  const resetDraft = useDraft((s) => s.reset);
  const setTable = useDraft((s) => s.setTable);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function enter() {
      const qrToken = params.qr_token;
      if (!qrToken) return;
      const { data, error: reqError } = await api.POST("/api/v1/guest/sessions/{qr_token}", { params: { path: { qr_token: qrToken } } });
      if (reqError) { setError("Could not open this table. Ask your server."); return; }
      const body = data as unknown as QrEntryResponse;
      tokens.setSession(body.token);
      resetDraft();
      setTable("guest-table", body.table_number, body.session_id);
      router.replace("/order?mode=qr");
    }
    void enter();
  }, [params.qr_token, resetDraft, router, setTable]);

  return <main className="guest-theme flex min-h-screen items-center justify-center px-4">{error ? <p className="text-center text-[var(--danger)]">{error}</p> : <p className="text-sm text-[var(--guest-ink-3)]">Opening menu…</p>}</main>;
}
