import type { StaffRole } from "@/lib/domain";
export function routeForRole(role: StaffRole): string {
  switch (role) {
    case "WAITER": return "/order";
    case "KITCHEN": return "/kds";
    case "CASHIER": return "/cashier";
    case "OWNER": return "/owner";
    case "MANAGER": return "/login/chooser";
    default: return "/login";
  }
}
