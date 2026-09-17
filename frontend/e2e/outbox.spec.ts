import { expect, test } from "@playwright/test";

/**
 * Full UI offline drain is covered by Vitest (`lib/outbox/outbox.test.ts`, including the
 * 30-minute-cut scenario). A Playwright version that combines `page.route` with a WAN-down
 * simulation currently leaves `fetch` hung mid-drain under Chromium on Windows.
 */
test.describe("offline outbox", () => {
  test("connectivity badge is on the order shell", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("renzy.device_token", "mock-device-token");
      window.localStorage.setItem("renzy.session_token", "mock-staff-jwt-ws07");
      window.localStorage.setItem(
        "renzy.device_meta",
        JSON.stringify({
          deviceId: "dev-1",
          label: "Floor 1",
          allowedRoles: ["WAITER", "CASHIER", "KITCHEN", "OWNER"],
        }),
      );
      window.localStorage.setItem(
        "renzy.staff",
        JSON.stringify({
          id: "b1000001-0001-4001-8001-000000000001",
          name: "Efua Mensah",
          role: "WAITER",
        }),
      );
    });

    await page.route("**/api/v1/tables", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ id: "t7", number: "7", seats: 4, open_session: null }]),
      });
    });
    await page.route("**/api/v1/menu", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ categories: [] }),
      });
    });

    await page.goto("/order");
    await expect(page.getByTestId("connectivity-badge")).toBeVisible();
    await expect(page.getByTestId("connectivity-badge")).toHaveAttribute("data-status", "online");
  });
});
