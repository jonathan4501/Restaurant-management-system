import { expect, test, type Page } from "@playwright/test";

/** The till sits on one machine by the door, signed in for the whole service. */
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("renzy.device_token", "mock-device-token");
    window.localStorage.setItem("renzy.session_token", "mock-staff-jwt-ws07");
    window.localStorage.setItem(
      "renzy.staff",
      JSON.stringify({
        id: "b1000002-0002-4002-8002-000000000002",
        name: "Akosua Boateng",
        role: "CASHIER",
      }),
    );
  });
});

async function openBillForTable7(page: Page) {
  await page.goto("/cashier");
  await page.getByTestId("bill-7").click();
  await expect(page.getByTestId("bill-total")).toContainText("133.00");
  await page.getByTestId("bill-pay").click();
  await expect(page.getByTestId("pay-sheet")).toBeVisible();
}

test("with no shift open, the till asks for the float before anything else", async ({ page }) => {
  // Prism serves one example per route, and during service the shift is open — so the
  // no-shift state is the one case that has to be asked for explicitly.
  await page.route("**/api/v1/shifts/current", (route) =>
    route.fulfill({ json: { shift: null } }),
  );

  await page.goto("/cashier");
  await expect(page.getByTestId("open-shift")).toBeVisible();

  await page.getByTestId("float-quick-20000").click();
  await expect(page.getByTestId("float-display")).toHaveText("GH₵ 200.00");

  const opened = page.waitForRequest(
    (request) => request.url().endsWith("/api/v1/shifts") && request.method() === "POST",
  );
  await page.getByTestId("open-shift-submit").click();
  const request = await opened;

  const body = request.postDataJSON() as { id: string; opening_float_pesewas: number };
  expect(body.opening_float_pesewas).toBe(20000);
  // The entity id is the idempotency key, so a double-tap replays rather than double-opening.
  expect(request.headers()["idempotency-key"]).toBe(body.id);

  await expect(page.getByTestId("till")).toBeVisible();
  await expect(page.getByTestId("bills-outstanding")).toHaveText("GH₵ 218.00");
});

test("a bill still in the kitchen is on the board but cannot be paid", async ({ page }) => {
  await page.goto("/cashier");
  await expect(page.getByTestId("bill-7")).toHaveAttribute("data-payable", "true");
  await expect(page.getByTestId("bill-3")).toHaveAttribute("data-payable", "false");
  await expect(page.getByTestId("bill-3")).toContainText("Cooking");
});

test("cash: the change is unmistakable and the bill settles", async ({ page }) => {
  await openBillForTable7(page);

  // The amount defaults to the whole balance — the common case is nobody splitting anything.
  await expect(page.getByTestId("pay-amount")).toHaveText("GH₵ 133.00");

  await page.getByTestId("tender-20000").click();
  await expect(page.getByTestId("pay-change")).toHaveText("GH₵ 67.00");

  const paid = page.waitForRequest(
    (request) => request.url().includes("/payments") && request.method() === "POST",
  );
  await page.getByTestId("pay-submit").click();
  const request = await paid;

  const body = request.postDataJSON() as {
    id: string;
    method: string;
    amount_pesewas: number;
    tendered_pesewas: number;
  };
  expect(body.method).toBe("CASH");
  expect(body.amount_pesewas).toBe(13300);
  expect(body.tendered_pesewas).toBe(20000);
  expect(request.headers()["idempotency-key"]).toBe(body.id);

  await expect(page.getByTestId("till-toast")).toHaveText("Paid in full");
});

test("a four-way split by MoMo needs the keyboard only for the reference", async ({ page }) => {
  await openBillForTable7(page);

  await page.getByTestId("split-4").click();
  await expect(page.getByTestId("pay-amount")).toHaveText("GH₵ 33.25");

  await page.getByTestId("method-MOMO_MTN").click();
  await page.getByTestId("pay-reference").fill("mp 2609 1234 5678");
  await expect(page.getByTestId("pay-reference-normalised")).toHaveText(
    "Stored as MP260912345678",
  );

  const paid = page.waitForRequest(
    (request) => request.url().includes("/payments") && request.method() === "POST",
  );
  await page.getByTestId("pay-submit").click();
  const body = (await paid).postDataJSON() as {
    method: string;
    amount_pesewas: number;
    tendered_pesewas: number | null;
    external_reference: string;
  };

  expect(body.method).toBe("MOMO_MTN");
  expect(body.amount_pesewas).toBe(3325);
  expect(body.tendered_pesewas).toBeNull();
  expect(body.external_reference).toBe("MP260912345678");
});

test("a no-sale opens the drawer only behind a manager's PIN and a reason", async ({ page }) => {
  await page.goto("/cashier");
  await page.getByTestId("till-drawer").click();
  await page.getByTestId("drawer-NO_SALE").click();
  await page.getByTestId("drawer-submit").click();

  await page.getByTestId("authorise-reason").selectOption("NO_SALE");
  for (const digit of "1234") await page.getByTestId(`pin-key-${digit}`).click();

  const recorded = page.waitForRequest(
    (request) => request.url().includes("/movements") && request.method() === "POST",
  );
  await page.getByTestId("pin-submit").click();
  const body = (await recorded).postDataJSON() as {
    kind: string;
    reason_code: string;
    authorisation: { token: string; reason_code: string };
  };

  expect(body.kind).toBe("NO_SALE");
  expect(body.reason_code).toBe("NO_SALE");
  // Both the actor and the authoriser have to reach the server, or the audit trail is a lie.
  expect(body.authorisation.token).toBeTruthy();
  expect(body.authorisation.reason_code).toBe("NO_SALE");

  await expect(page.getByTestId("till-toast")).toHaveText("Drawer opened");
});

test("closing the shift declares first, then shows the variance and the money taken", async ({
  page,
}) => {
  await page.goto("/cashier");
  await page.getByTestId("till-close-shift").click();
  await expect(page.getByTestId("close-shift")).toBeVisible();

  // Counting is blind on purpose: the expected figure must not be on screen while counting.
  await expect(page.getByTestId("close-shift")).not.toContainText("Expected in drawer");

  for (const key of ["3", "3", "0", "00"]) await page.getByTestId(`declared-${key}`).click();
  await expect(page.getByTestId("declared-display")).toHaveText("GH₵ 330.00");

  await page.getByTestId("close-shift-submit").click();

  await expect(page.getByTestId("z-report")).toBeVisible();
  await expect(page.getByTestId("z-money-taken")).toHaveText("GH₵ 166.25");
  await expect(page.getByTestId("z-variance")).toHaveAttribute("data-balanced", "false");
  await expect(page.getByTestId("z-variance")).toContainText("-GH₵ 3.00");
  await expect(page.getByTestId("z-variance")).toContainText("short");

  // ADR-0005: no tax anywhere, and the gross figure is never called revenue or profit.
  const report = await page.getByTestId("close-shift").innerText();
  expect(report).toMatch(/Money taken/);
  expect(report).not.toMatch(/VAT|NHIL|GETFund|Revenue|Profit/i);
});
