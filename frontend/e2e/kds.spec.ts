import { expect, test } from "@playwright/test";

/** The kitchen display runs signed in on a fixed screen, so seed the tokens and go straight there. */
test.beforeEach(async ({ page }) => {
  // Runs on every navigation, so it must not clear storage: the station choice has to survive a reload.
  await page.addInitScript(() => {
    window.localStorage.setItem("renzy.device_token", "mock-device-token");
    window.localStorage.setItem("renzy.session_token", "mock-staff-jwt-ws07");
    window.localStorage.setItem(
      "renzy.staff",
      JSON.stringify({ id: "b1000003-0003-4003-8003-000000000003", name: "Yaw Mensah", role: "KITCHEN" }),
    );
  });
});

test("tickets sit in the right columns, and an old one is unmistakable", async ({ page }) => {
  await page.goto("/kds");

  await expect(page.getByTestId("column-SUBMITTED").getByTestId("ticket-1001")).toBeVisible();
  await expect(page.getByTestId("column-PREPARING").getByTestId("ticket-1002")).toBeVisible();
  await expect(page.getByTestId("column-READY").getByTestId("ticket-1003")).toBeVisible();

  // Submitted in 2020: hours old, so it must be flagged late, not merely amber.
  await expect(page.getByTestId("ticket-1001")).toHaveAttribute("data-urgency", "late");
  await expect(page.getByTestId("ticket-age-1001")).not.toHaveText("00:00");

  // Modifiers and notes are on the card — the cook never opens anything to read the order.
  await expect(page.getByTestId("ticket-1001")).toContainText("Extra hot");
  await expect(page.getByTestId("ticket-1001")).toContainText("no onions");
});

test("a new ticket is accepted with one tap", async ({ page }) => {
  await page.goto("/kds");
  const acked = page.waitForRequest(
    (request) => request.url().includes("/orders/o-1001/ack") && request.method() === "POST",
  );
  await page.getByTestId("ack-1001").click();
  const request = await acked;
  expect(request.headers()["idempotency-key"]).toBeTruthy();
});

test("the card moves the moment it is tapped, outlined until the server agrees", async ({ page }) => {
  // Hold the ack open: what the cook sees while the command is in flight is the point of the test.
  await page.route("**/orders/o-1001/ack", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await page.goto("/kds");
  await expect(page.getByTestId("column-SUBMITTED").getByTestId("ticket-1001")).toBeVisible();
  await page.getByTestId("ack-1001").click();

  const moved = page.getByTestId("column-PREPARING").getByTestId("ticket-1001");
  await expect(moved).toBeVisible();
  await expect(moved).toHaveAttribute("data-pending", "true");
});

test("the grill cook sees only grill lines", async ({ page }) => {
  await page.goto("/kds");
  const grillRequest = page.waitForRequest((r) => r.url().includes("station=GRILL"));
  await page.getByTestId("station-grill").click();
  await grillRequest;
  await expect(page.getByTestId("station-grill")).toHaveAttribute("aria-selected", "true");

  // The choice survives a reload: the screen by the grill stays the grill screen.
  await page.reload();
  await expect(page.getByTestId("station-grill")).toHaveAttribute("aria-selected", "true");
});

test("86 takes an item off the menu and says so", async ({ page }) => {
  await page.goto("/kds");
  await page.getByTestId("kds-86").click();
  await page.getByTestId("eighty-six-filter").fill("Jollof");

  const target = page.locator('[data-testid^="eighty-six-"][data-available="true"]').first();
  await expect(target).toBeVisible();
  const eightySixed = page.waitForRequest((r) => /\/menu\/items\/.+\/86$/.test(r.url()));
  await target.click();
  await eightySixed;

  await expect(page.getByTestId("kds-toast")).toBeVisible();
  await expect(page.getByTestId("kds-toast")).toContainText("Jollof");
});
