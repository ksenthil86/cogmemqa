import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

test("task6-01 graph canvas container is present in DOM", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({ path: `${SCREENSHOTS}/task6-01-graph-canvas-present.png` });
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
});

test("task6-02 page shows loading or error state (backend may not be running)", async ({ page }) => {
  await page.goto("/");
  // Wait a bit for fetch to complete or fail
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${SCREENSHOTS}/task6-02-after-fetch-attempt.png` });

  const loading = page.getByTestId("graph-loading");
  const error = page.getByTestId("graph-error");
  const canvas = page.getByTestId("graph-canvas");

  // Canvas container must always be present
  await expect(canvas).toBeVisible();

  // Either loading, error, or nvl wrapper should be in DOM
  const loadingVisible = await loading.isVisible().catch(() => false);
  const errorVisible = await error.isVisible().catch(() => false);

  // At least one state indicator or NVL wrapper should be rendered
  const anyStateShown =
    loadingVisible ||
    errorVisible ||
    (await page.locator("[data-testid='graph-canvas'] > div").count()) > 0;

  expect(anyStateShown).toBe(true);
});

test("task6-03 page title still shows CoGMEM Inspector after GraphCanvas added", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({ path: `${SCREENSHOTS}/task6-03-title-with-canvas.png` });
  await expect(page.getByTestId("page-title")).toHaveText("CoGMEM Inspector");
  await expect(page).toHaveTitle(/CoGMEM/);
});
