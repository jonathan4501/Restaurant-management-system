import { expect, test } from "@playwright/test";

const JOLLOF_ID = "60c90854-cbda-59e0-81c2-326fdfc47793";
const GUINEA_ID = "0f9cb040-bd96-558a-b146-512aa33c8c1b";
const PLANTAIN_ID = "fcad2e62-ac05-5202-b259-69907ab3b43c";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { window.localStorage.clear(); });
});

test("waiter login → table 7 → jollof + plantain → send", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("enrolment-code").fill("RENZY-DEV");
  await page.getByTestId("enrol-submit").click();
  await page.getByTestId("staff-efua").click();
  for (const digit of "1234") await page.getByTestId(`pin-key-${digit}`).click();
  await page.getByTestId("pin-submit").click();
  await expect(page).toHaveURL(/\/order$/);
  await page.getByTestId("table-7").click();
  await expect(page.getByTestId("active-table")).toContainText("7");
  await page.getByTestId(`menu-item-${JOLLOF_ID}`).click();
  await page.getByTestId(`modifier-${PLANTAIN_ID}`).click();
  await page.getByTestId("modifier-add").click();
  await expect(page.getByTestId("draft-total")).toContainText("83.00");
  await page.getByTestId("send-to-kitchen").click();
  await expect(page.getByTestId("order-sent")).toBeVisible();
});

test("86'd guinea fowl is not addable", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("enrolment-code").fill("RENZY-DEV");
  await page.getByTestId("enrol-submit").click();
  await page.getByTestId("staff-efua").click();
  for (const digit of "1234") await page.getByTestId(`pin-key-${digit}`).click();
  await page.getByTestId("pin-submit").click();
  await page.getByTestId("table-7").click();
  const guinea = page.getByTestId(`menu-item-${GUINEA_ID}`);
  await expect(guinea).toHaveAttribute("data-available", "false");
  await expect(guinea).toBeDisabled();
});
