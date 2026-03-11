/**
 * E2E: intake → generation stream → course view → lesson complete → feedback (PRD T-011).
 *
 * Prerequisites:
 * - Backend running (e.g. uvicorn syllabus.api.main:app --reload)
 * - Test user in ALLOWED_EMAILS. Set E2E_TEST_EMAIL and E2E_TEST_PASSWORD in env,
 *   or the test will skip. Run from web/: npm run test:e2e
 */

import { expect, test } from "@playwright/test";

const TEST_EMAIL = process.env.E2E_TEST_EMAIL;
const TEST_PASSWORD = process.env.E2E_TEST_PASSWORD;

test.describe("intake to course flow", () => {
  test.skip(
    !TEST_EMAIL || !TEST_PASSWORD,
    "Set E2E_TEST_EMAIL and E2E_TEST_PASSWORD (user must be in ALLOWED_EMAILS)"
  );

  test("login → intake → generate → course view → lesson complete → feedback", async ({
    page,
  }) => {
    await page.goto("/login");

    await page.getByLabel(/email/i).fill(TEST_EMAIL!);
    await page.getByLabel(/password/i).fill(TEST_PASSWORD!);
    await page.getByRole("button", { name: /sign in|log in/i }).click();

    await expect(page).toHaveURL(/\//);
    await expect(
      page.getByRole("link", { name: /Create your course|Create another course/i })
    ).toBeVisible({ timeout: 10000 });

    await page.goto("/intake");
    await expect(page.getByText("Create your course")).toBeVisible();

    await page.getByRole("radio", { name: "Newly diagnosed" }).click();
    await page.getByRole("button", { name: "Next" }).click();

    await page.getByRole("radio", { name: "PCOS" }).click();
    await page.getByRole("button", { name: "Next" }).click();

    await page.getByPlaceholder(/stim protocols|confusion/i).fill("I want to understand my options.");
    await page.getByRole("button", { name: "Next" }).click();

    await page.getByRole("button", { name: "Generate my course" }).click();

    await expect(page).toHaveURL(/\/generate\//, { timeout: 15000 });
    await expect(page.getByText("Building your course")).toBeVisible();

    await expect(page).toHaveURL(/\/course\//, { timeout: 120000 });

    await expect(page.getByRole("link", { name: "← Dashboard" })).toBeVisible();
    await expect(page.getByText("What to ask your RE").first()).toBeVisible({ timeout: 10000 });

    const firstLessonButton = page.getByRole("navigation").getByRole("button").first();
    await firstLessonButton.click();

    await page.getByRole("button", { name: "Yes", exact: false }).click();
    await expect(page.getByText("Thanks for your feedback")).toBeVisible({ timeout: 5000 });
  });
});
