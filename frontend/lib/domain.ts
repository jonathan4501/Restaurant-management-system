/**
 * Domain shapes for ordering UI.
 */
export type StaffRole = "WAITER" | "KITCHEN" | "CASHIER" | "MANAGER" | "OWNER";
export type TableStateChip = "free" | "seated" | "ordered" | "food_ready" | "awaiting_payment";
export type ModifierSelection = "ONE" | "MANY";
export type OrderMode = "waiter" | "guest" | "qr";
export type AuthPurpose =
  | "VOID_AFTER_ACK" | "DISCOUNT" | "COMP" | "PRICE_OVERRIDE" | "REOPEN"
  | "DRAWER_MOVEMENT" | "PAYMENT_VOID" | "PRICE_CHANGE_IN_SERVICE" | "GUEST_EXIT";

export interface StaffSummary { id: string; full_name: string; role: StaffRole; initials?: string; }
export interface DeviceMe { id: string; label: string; allowed_roles: StaffRole[]; staff: StaffSummary[]; }
export interface Modifier { id: string; name: string; price_pesewas: number; is_default: boolean; is_available: boolean; sort_order: number; }
export interface ModifierGroup { id: string; name: string; selection: ModifierSelection; is_required: boolean; sort_order: number; modifiers: Modifier[]; }
export interface MenuItem { id: string; name: string; description: string | null; image_url: string | null; price_pesewas: number; prep_station: "KITCHEN" | "GRILL" | "BAR"; is_available: boolean; modifier_groups: ModifierGroup[]; }
export interface MenuCategory { id: string; name: string; sort_order: number; items: MenuItem[]; }
export interface MenuResponse { categories: MenuCategory[]; }
export interface OpenSessionSummary { id: string; opened_at: string; party_size: number; seated_minutes: number; bill_total_pesewas: number; paid_pesewas: number; order_count: number; }
export interface TableRow { id: string; number: string; seats: number | null; state_chip: TableStateChip; open_session: OpenSessionSummary | null; }
export interface DraftModifier { id: string; name: string; price_pesewas: number; }
export interface DraftLine { client_id: string; menu_item_id: string; name_snapshot: string; unit_price_pesewas: number; quantity: number; modifiers: DraftModifier[]; notes: string; }

export function lineTotalPesewas(line: DraftLine): number {
  return (line.unit_price_pesewas + line.modifiers.reduce((s, m) => s + m.price_pesewas, 0)) * line.quantity;
}
export function draftTotalPesewas(lines: DraftLine[]): number {
  return lines.reduce((s, l) => s + lineTotalPesewas(l), 0);
}
