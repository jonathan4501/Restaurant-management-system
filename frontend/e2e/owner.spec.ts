import { expect, test, type Page, type Route } from "@playwright/test";

const OWNER = {
  id: "a1000001-0001-4001-8001-000000000001",
  name: "Ama Owner",
  email: "owner@renzy.gh",
  role: "OWNER" as const,
  restaurant_id: "r1000001-0001-4001-8001-000000000001",
};

const VARIANCE = {
  date_from: "2026-09-10",
  date_to: "2026-09-16",
  voids_after_acknowledgement: [
    {
      order_id: "o1000001-0001-4001-8001-000000000001",
      order_number: 1042,
      table_number: "9",
      value_pesewas: 19500,
      status_at_void: "PREPARING",
      reason_code: "WRONG_TABLE",
      actor: "Kofi Asante",
      actor_role: "WAITER",
      authorised_by: "Ama Mensah",
      at: "2026-09-16T19:21:00Z",
    },
  ],
  void_value_pesewas: 19500,
  discounts_by_staff: [
    {
      staff: "Kofi Asante",
      staff_id: "b1000001-0001-4001-8001-000000000001",
      discount_count: 2,
      discount_pesewas: 5000,
      comp_count: 1,
      comp_pesewas: 3400,
      value_pesewas: 8400,
    },
  ],
  discount_pesewas: 5000,
  comp_pesewas: 3400,
  reopened_bills: [
    {
      session_id: "s1000001-0001-4001-8001-000000000001",
      table_number: "12",
      trigger: "MANAGER",
      orders_reopened: 1,
      reason_code: "ADD_ITEMS",
      actor: "Ama Mensah",
      authorised_by: "Ama Mensah",
      at: "2026-09-16T19:28:00Z",
    },
  ],
  reopened_count: 1,
  manager_reopens: 1,
  cash_variance_by_shift: [
    {
      shift_id: "f1000001-0001-4001-8001-000000000001",
      cashier: "Ama Mensah",
      cashier_id: "b1000002-0002-4002-8002-000000000002",
      opened_at: "2026-09-16T10:00:00Z",
      closed_at: "2026-09-16T22:00:00Z",
      expected_cash_pesewas: 246300,
      declared_cash_pesewas: 241800,
      variance_pesewas: -4500,
    },
  ],
  cash_variance_pesewas: -4500,
  order_number_gaps: [{ business_date: "2026-09-16", missing: [1040] }],
};

const TODAY = {
  business_date: "2026-09-16",
  money_taken_pesewas: 579000,
  covers: 47,
  bills_settled: 47,
  average_bill_pesewas: 12319,
  open_bills: 5,
  open_balance_pesewas: 42000,
  orders_closed: 52,
};

const PATTERNS = {
  date_from: "2026-09-10",
  date_to: "2026-09-16",
  money_taken_pesewas: 579000,
  money_taken_by_hour: [
    { hour: 12, money_taken_pesewas: 80000 },
    { hour: 13, money_taken_pesewas: 150000 },
    { hour: 14, money_taken_pesewas: 120000 },
  ],
  payment_method_mix: {
    CASH: 237390,
    MOMO_MTN: 220020,
    MOMO_TELECEL: 69480,
    CARD: 52110,
  },
  best_sellers_by_value: [
    { name: "Banku with Grilled Tilapia", quantity: 14, value_pesewas: 168000 },
    { name: "Jollof Rice with Grilled Chicken", quantity: 22, value_pesewas: 165000 },
  ],
  station_timing: [
    { station: "KITCHEN", average_seconds: 720, lines: 40 },
    { station: "GRILL", average_seconds: 540, lines: 18 },
  ],
};

const EVENTS = {
  events: [
    {
      seq: 100,
      type: "ORDER_VOIDED",
      aggregate_type: "ORDER",
      aggregate_id: "o1000001-0001-4001-8001-000000000001",
      order_id: "o1000001-0001-4001-8001-000000000001",
      actor_id: "b1000001-0001-4001-8001-000000000001",
      actor: "Kofi Asante",
      actor_role: "WAITER",
      authorised_by: "Ama Mensah",
      reason_code: "WRONG_TABLE",
      flagged: true,
      created_at: "2026-09-16T19:21:00Z",
      payload: { order_number: 1042 },
    },
    {
      seq: 99,
      type: "ORDER_SUBMITTED",
      aggregate_type: "ORDER",
      aggregate_id: "o1000002-0002-4002-8002-000000000002",
      order_id: "o1000002-0002-4002-8002-000000000002",
      actor_id: "b1000001-0001-4001-8001-000000000001",
      actor: "Kofi Asante",
      actor_role: "WAITER",
      authorised_by: null,
      reason_code: null,
      flagged: false,
      created_at: "2026-09-16T19:14:00Z",
      payload: { order_number: 1048 },
    },
    {
      seq: 98,
      type: "PAYMENT_RECORDED",
      aggregate_type: "SESSION",
      aggregate_id: "s1000001-0001-4001-8001-000000000001",
      order_id: null,
      actor_id: "b1000002-0002-4002-8002-000000000002",
      actor: "Ama Mensah",
      actor_role: "CASHIER",
      authorised_by: null,
      reason_code: null,
      flagged: false,
      created_at: "2026-09-16T19:10:00Z",
      payload: { method: "MOMO_MTN" },
    },
  ],
  next_cursor: null,
  has_more: false,
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockOwnerApi(page: Page) {
  let authed = false;

  await page.route("**/api/v1/auth/owner/me", async (route) => {
    if (!authed) {
      await fulfillJson(
        route,
        {
          type: "about:blank",
          title: "Unauthorized",
          status: 401,
          code: "token_invalid",
          detail: "Log in first",
          errors: {},
        },
        401,
      );
      return;
    }
    await fulfillJson(route, OWNER);
  });

  await page.route("**/api/v1/auth/owner/login", async (route) => {
    await fulfillJson(route, { totp_required: true });
  });

  await page.route("**/api/v1/auth/owner/totp", async (route) => {
    authed = true;
    await fulfillJson(route, { ok: true });
  });

  await page.route("**/api/v1/auth/logout", async (route) => {
    authed = false;
    await fulfillJson(route, { ok: true });
  });

  await page.route("**/api/v1/reports/variance**", async (route) => {
    await fulfillJson(route, VARIANCE);
  });
  await page.route("**/api/v1/reports/today**", async (route) => {
    await fulfillJson(route, TODAY);
  });
  await page.route("**/api/v1/reports/patterns**", async (route) => {
    await fulfillJson(route, PATTERNS);
  });
  await page.route("**/api/v1/events/log**", async (route) => {
    const url = new URL(route.request().url());
    const actorId = url.searchParams.get("actor_id");
    if (actorId) {
      await fulfillJson(route, {
        events: EVENTS.events.filter((e) => e.actor_id === actorId),
        next_cursor: null,
        has_more: false,
      });
      return;
    }
    await fulfillJson(route, EVENTS);
  });

  // Quiet the live stream so the dashboard does not spin on Prism.
  await page.route("**/api/v1/stream**", async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/v1/events?**", async (route) => {
    await fulfillJson(route, { events: [], last_seq: 0, has_more: false });
  });
}

test("owner login with TOTP → variance panel → log filter by staff", async ({ page }) => {
  await mockOwnerApi(page);

  await page.goto("/owner");
  await expect(page.getByTestId("owner-email")).toBeVisible();

  await page.getByTestId("owner-email").fill("owner@renzy.gh");
  await page.getByTestId("owner-password").fill("a-long-enough-password");
  await page.getByTestId("owner-login-submit").click();

  await expect(page.getByTestId("owner-totp")).toBeVisible();
  await page.getByTestId("owner-totp").fill("123456");
  await page.getByTestId("owner-totp-submit").click();

  await expect(page.getByTestId("variance-panel")).toBeVisible();
  await expect(page.getByTestId("leak-cash")).toContainText("-GH₵ 45.00");
  await expect(page.getByTestId("today-money-taken")).toContainText("Money taken");
  await expect(page.getByTestId("today-money-taken")).toContainText("5,790.00");

  await page.getByTestId("owner-nav-events").click();
  await expect(page.getByTestId("event-log")).toBeVisible();
  await expect(page.getByTestId("log-row-100")).toBeVisible();

  await page.getByTestId("log-filter-staff").selectOption("b1000001-0001-4001-8001-000000000001");
  await page.getByTestId("log-filter-apply").click();
  await expect(page.getByTestId("log-row-100")).toBeVisible();
  await expect(page.getByTestId("log-row-98")).toHaveCount(0);
});
