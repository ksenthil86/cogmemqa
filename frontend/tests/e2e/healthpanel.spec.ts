import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

const MOCK_PARTIAL = {
  coverage_pct: 87.5,
  covered_ac: 7,
  total_ac: 8,
  open_findings_count: 2,
  by_severity: { low: 1, medium: 1, high: 0 },
  report_count: 3,
};

const MOCK_FULL = {
  coverage_pct: 100.0,
  covered_ac: 8,
  total_ac: 8,
  open_findings_count: 0,
  by_severity: { low: 0, medium: 0, high: 0 },
  report_count: 5,
};

function mockHealth(page: import("@playwright/test").Page, body: object) {
  return page.route("**/api/health", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) })
  );
}

test("task8-01 health panel shows skeleton loading state before fetch resolves", async ({ page }) => {
  // Delay response so loading state is visible during screenshot
  await page.route("**/api/health", async (route) => {
    await new Promise<void>((r) => setTimeout(r, 800));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_PARTIAL),
    });
  });

  await page.goto("/health-test");
  // Screenshot taken before the delayed response resolves
  await page.screenshot({ path: `${SCREENSHOTS}/task8-01-loading-skeleton.png` });
  await expect(page.getByTestId("health-skeleton")).toBeVisible();
});

test("task8-02 health panel renders all 4 metric cards after fetch", async ({ page }) => {
  await mockHealth(page, MOCK_PARTIAL);
  await page.goto("/health-test");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task8-02-all-cards.png` });

  await expect(page.getByTestId("health-panel")).toBeVisible();
  await expect(page.getByTestId("health-coverage")).toBeVisible();
  await expect(page.getByTestId("health-findings")).toBeVisible();
  await expect(page.getByTestId("health-reports")).toBeVisible();
  await expect(page.getByTestId("health-status")).toBeVisible();
});

test("task8-03 coverage card shows covered/total ACs and percentage", async ({ page }) => {
  await mockHealth(page, MOCK_PARTIAL);
  await page.goto("/health-test");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task8-03-coverage-card.png` });

  await expect(page.getByTestId("health-coverage")).toContainText("7/8 ACs");
  await expect(page.getByTestId("health-coverage")).toContainText("87.5%");
});

test("task8-04 status shows HEALTHY when coverage=100 and no open findings", async ({ page }) => {
  await mockHealth(page, MOCK_FULL);
  await page.goto("/health-test");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task8-04-healthy-status.png` });

  await expect(page.getByTestId("health-status")).toHaveText("HEALTHY");
});

test("task8-05 status shows NEEDS REVIEW when coverage < 100 or findings exist", async ({ page }) => {
  await mockHealth(page, MOCK_PARTIAL);
  await page.goto("/health-test");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task8-05-needs-review.png` });

  await expect(page.getByTestId("health-status")).toHaveText("NEEDS REVIEW");
});

test("task8-06 findings card shows total count and low/medium/high breakdown", async ({ page }) => {
  await mockHealth(page, MOCK_PARTIAL);
  await page.goto("/health-test");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task8-06-findings-breakdown.png` });

  const card = page.getByTestId("health-findings");
  await expect(card).toContainText("2");
  await expect(card).toContainText("low 1");
  await expect(card).toContainText("med 1");
  await expect(card).toContainText("high 0");
});

test("task8-07 shows error state when API is unreachable", async ({ page }) => {
  await page.route("**/api/health", (route) => route.abort());
  await page.goto("/health-test");
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${SCREENSHOTS}/task8-07-error-state.png` });

  await expect(page.getByTestId("health-error")).toBeVisible();
});
