import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

test("task5-01 placeholder page loads and shows CoGMEM Inspector heading", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({ path: `${SCREENSHOTS}/task5-01-placeholder-page.png` });
  await expect(page.getByTestId("page-title")).toHaveText("CoGMEM Inspector");
});

test("task5-02 page title is CoGMEM Inspector in document head", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({ path: `${SCREENSHOTS}/task5-02-page-title.png` });
  await expect(page).toHaveTitle(/CoGMEM/);
});
