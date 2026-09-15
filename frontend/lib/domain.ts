/**
 * Domain shapes for ordering UI.
 *
 * The backend documents most response bodies as untyped objects, so these mirror what the Django views
 * actually return (apps/accounts/views.py, apps/orders/serializers_read.py, apps/menu/serializers.py).
 * Request bodies and paths come from the generated lib/api/schema.d.ts.
 */
export type StaffRole = "WAITER" | "KITCHEN" | "CASHIER" | "MANAGER" | "OWNER";
/** apps/floor/state_chip.py, plus "free" (no open session) and "seated" (open, nothing sent yet). */
export type SessionState = "sent" | "cooking" | "food_ready" | "ready_to_pay" | "part_paid";
export type TableStateChip = "free" | "seated" | SessionState;
export type ModifierSelection = "ONE" | "MANY";
export type OrderMode = "waiter" | "guest" | "qr";
export type AuthPurpose =
  | "VOID_AFTER_ACK" | "DISCOUNT" | "COMP" | "PRICE_OVERRIDE" | "REOPEN"
  | "DRAWER_MOVEMENT" | "PAYMENT_VOID" | "PRICE_CHANGE_IN_SERVICE";

export interface StaffSummary { id: string; name: string; role: StaffRole; }
export interface DeviceMe { device_id: string; label: string; allowed_roles: StaffRole[]; staff: StaffSummary[]; }
export interface PinLoginResponse { token: string; expires_at: string; staff: StaffSummary; }
export interface EnrolResponse { device_id: string; device_token: string; allowed_roles: StaffRole[]; label?: string; }
export interface QrEntryResponse { token: string; expires_in: number; session_id: string; table_number: string; mode: "qr"; }
export interface Modifier { id: string; name: string; price_pesewas: number; is_default: boolean; is_available: boolean; sort_order: number; }
export interface ModifierGroup { id: string; name: string; selection: ModifierSelection; is_required: boolean; sort_order: number; modifiers: Modifier[]; }
export interface MenuItem { id: string; name: string; description: string | null; image_url: string | null; price_pesewas: number; prep_station: "KITCHEN" | "GRILL" | "BAR"; is_available: boolean; sort_order?: number; modifier_groups: ModifierGroup[]; }
export interface MenuCategory { id: string; name: string; sort_order: number; items: MenuItem[]; }
export interface MenuResponse { categories: MenuCategory[]; }
export interface OpenSessionSummary { id: string; opened_at: string; bill_total_pesewas: number; paid_pesewas: number; balance_pesewas: number; order_count: number; state: SessionState | null; }
export interface TableRow { id: string; number: string; seats: number | null; is_active: boolean; open_session: OpenSessionSummary | null; }
export interface DraftModifier { id: string; name: string; price_pesewas: number; }
export interface DraftLine { client_id: string; menu_item_id: string; name_snapshot: string; unit_price_pesewas: number; quantity: number; modifiers: DraftModifier[]; notes: string; }

export function tableChip(table: TableRow): TableStateChip {
  if (!table.open_session) return "free";
  return table.open_session.state ?? "seated";
}

/** "1", "2", … "10" rather than the backend's string order "1", "10", "11", "2". */
export function sortTables(tables: TableRow[]): TableRow[] {
  return [...tables].sort((a, b) => a.number.localeCompare(b.number, undefined, { numeric: true }));
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : parts[0]?.[1] ?? "")).toUpperCase();
}

export function lineTotalPesewas(line: DraftLine): number {
  return (line.unit_price_pesewas + line.modifiers.reduce((s, m) => s + m.price_pesewas, 0)) * line.quantity;
}
export function draftTotalPesewas(lines: DraftLine[]): number {
  return lines.reduce((s, l) => s + lineTotalPesewas(l), 0);
}
