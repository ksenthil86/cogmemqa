import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

const MOCK_GRAPH = {
  nodes: [
    { id: "node-1", labels: ["Requirement"], properties: { id: "req-account-opening" } },
    { id: "node-2", labels: ["Functionality"], properties: { id: "func-account-opening" } },
  ],
  relationships: [
    { id: "rel-1", type: "REALIZED_BY", startNodeId: "node-1", endNodeId: "node-2", properties: {} },
  ],
};

const MOCK_EXPAND = {
  nodes: [
    { id: "node-1", labels: ["Requirement"], properties: { id: "req-account-opening" } },
    { id: "node-3", labels: ["Component"], properties: { id: "comp-account-opening" } },
  ],
  relationships: [
    { id: "rel-2", type: "COMPOSED_OF", startNodeId: "node-2", endNodeId: "node-3", properties: {} },
  ],
};

// NVL renders two <canvas> elements:
//   nvl-gl-canvas  (opacity:0 — WebGL layer)
//   nvl-c2d-canvas (opacity:1 — 2D label layer, always visible)
// and a wrapper div[data-testid="nvl-parent"]

test("task7-01 NVL renders visible canvas when API returns graph data", async ({ page }) => {
  await page.route("**/api/graph", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );

  await page.goto("/");
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${SCREENSHOTS}/task7-01-canvas-with-data.png` });

  // Loading state cleared
  await expect(page.getByTestId("graph-loading")).not.toBeVisible();
  await expect(page.getByTestId("graph-error")).not.toBeVisible();

  // NVL renders its parent wrapper and the visible 2D canvas
  await expect(page.getByTestId("nvl-parent")).toBeVisible();
  await expect(page.getByTestId("nvl-c2d-canvas")).toBeVisible();
});

test("task7-02 expand route is set up — mock responds when called", async ({ page }) => {
  let expandCallCount = 0;

  await page.route("**/api/graph", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/graph/expand**", (route) => {
    expandCallCount++;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EXPAND),
    });
  });

  const jsErrors: string[] = [];
  page.on("pageerror", (err) => jsErrors.push(err.message));

  await page.goto("/");
  await page.waitForTimeout(1000);
  await expect(page.getByTestId("nvl-parent")).toBeVisible();

  // Click the centre of the NVL 2D canvas — may or may not hit a rendered node
  const nvlCanvas = page.getByTestId("nvl-c2d-canvas");
  const box = await nvlCanvas.boundingBox();
  if (box) {
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(500);
  }

  await page.screenshot({ path: `${SCREENSHOTS}/task7-02-after-canvas-click.png` });

  // No unexpected JS errors
  const unexpectedErrors = jsErrors.filter(
    (e) => !e.includes("Failed to fetch") && !e.includes("NetworkError")
  );
  expect(unexpectedErrors).toHaveLength(0);
});

test("task7-03 no JS errors during full lifecycle with mocked graph", async ({ page }) => {
  const jsErrors: string[] = [];
  page.on("pageerror", (err) => jsErrors.push(err.message));

  await page.route("**/api/graph", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/graph/expand**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EXPAND) })
  );

  await page.goto("/");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${SCREENSHOTS}/task7-03-no-errors.png` });

  await expect(page.getByTestId("page-title")).toHaveText("CoGMEM Inspector");

  const unexpectedErrors = jsErrors.filter(
    (e) => !e.includes("Failed to fetch") && !e.includes("NetworkError")
  );
  expect(unexpectedErrors).toHaveLength(0);
});

test("task7-04 NVL canvas remains visible after multi-click interactions", async ({ page }) => {
  await page.route("**/api/graph", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/graph/expand**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EXPAND) })
  );

  await page.goto("/");
  await page.waitForTimeout(1000);
  await expect(page.getByTestId("nvl-c2d-canvas")).toBeVisible();

  const nvlCanvas = page.getByTestId("nvl-c2d-canvas");
  const box = await nvlCanvas.boundingBox();
  if (box) {
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.3);
    await page.waitForTimeout(300);
    await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.7);
    await page.waitForTimeout(300);
  }

  await page.screenshot({ path: `${SCREENSHOTS}/task7-04-canvas-after-clicks.png` });
  await expect(page.getByTestId("nvl-c2d-canvas")).toBeVisible();
});
