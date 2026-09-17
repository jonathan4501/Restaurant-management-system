/** Display labels for the owner back office. Gross figures stay "Money taken" / "Total collected". */

export const MONEY_TAKEN = "Money taken";
export const TOTAL_COLLECTED = "Total collected";

const METHOD_LABELS: Record<string, string> = {
  CASH: "Cash",
  MOMO_MTN: "MTN MoMo",
  MOMO_TELECEL: "Telecel Cash",
  MOMO_AT: "AT MoMo",
  CARD: "Card",
  BANK: "Bank",
};

export function paymentMethodLabel(method: string): string {
  return METHOD_LABELS[method] ?? method.replaceAll("_", " ");
}

export function formatSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}
