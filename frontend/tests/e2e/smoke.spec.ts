/**
 * Sprint v6 integration smoke — verifies the complete inspector dashboard.
 * All APIs are mocked so the test requires only the Next.js dev server.
 */
import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

const MOCK_HEALTH = {
  coverage_pct: 100.0,
  covered_ac: 10,
  total_ac: 10,
  open_findings_count: 1,
  by_severity: { low: 1, medium: 0, high: 0 },
  report_count: 5,
};

const MOCK_GRAPH = {
  nodes: [
    { id: "n1", labels: ["Requirement"], properties: { id: "req-account-opening" } },
    { id: "n2", labels: ["Functionality"], properties: { id: "func-account-opening" } },
    { id: "n3", labels: ["Component"], properties: { id: "comp-account-opening" } },
    { id: "n4", labels: ["File"], properties: { id: "src/account/AccountController.java" } },
  ],
  relationships: [
    { id: "r1", type: "REALIZED_BY", startNodeId: "n1", endNodeId: "n2", properties: {} },
    { id: "r2", type: "COMPOSED_OF", startNodeId: "n2", endNodeId: "n3", properties: {} },
    { id: "r3", type: "IMPLEMENTED_BY", startNodeId: "n3", endNodeId: "n4", properties: {} },
  ],
};

const MOCK_EXPAND = { nodes: [], relationships: [] };

const MOCK_AUDIT = {
  req_id: "req-account-opening",
  chain: [
    {
      req: "req-account-opening",
      req_title: "Account Opening",
      func: "func-account-opening",
      comp: "comp-account-opening",
      file: "src/account/AccountController.java",
      commit_sha: "b800001",
    },
  ],
};

test("task10-01 full inspector dashboard renders all panels", async ({ page }) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_HEALTH) })
  );
  await page.route("**/api/graph", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/graph/expand**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EXPAND) })
  );
  await page.route("**/api/audit/**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_AUDIT) })
  );

  await page.goto("/");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${SCREENSHOTS}/task10-01-full-dashboard.png` });

  // Header
  await expect(page.getByTestId("page-title")).toHaveText("CoGMEM Inspector");

  // Sidebar present with correct width
  const sidebar = page.getByTestId("sidebar");
  await expect(sidebar).toBeVisible();
  const box = await sidebar.boundingBox();
  expect(box?.width).toBeCloseTo(280, -1);

  // HealthPanel loaded — status card shows
  await expect(page.getByTestId("health-status")).toBeVisible();

  // AuditPanel default state
  await expect(page.getByTestId("audit-empty")).toBeVisible();

  // NVL graph canvas renders
  await expect(page.getByTestId("nvl-c2d-canvas")).toBeVisible();
});

test("task10-02 health panel shows NEEDS REVIEW (one low finding)", async ({ page }) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_HEALTH) })
  );
  await page.route("**/api/graph", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/graph/expand**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EXPAND) })
  );

  await page.goto("/");
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${SCREENSHOTS}/task10-02-health-status.png` });

  // 1 open finding → NEEDS REVIEW even at 100% coverage
  await expect(page.getByTestId("health-status")).toHaveText("NEEDS REVIEW");
  await expect(page.getByTestId("health-coverage")).toContainText("10/10 ACs");
  await expect(page.getByTestId("health-coverage")).toContainText("100.0%");
});

test("task10-03 no JS errors during complete dashboard lifecycle", async ({ page }) => {
  const jsErrors: string[] = [];
  page.on("pageerror", (err) => jsErrors.push(err.message));

  await page.route("**/api/health", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_HEALTH) })
  );
  await page.route("**/api/graph", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/graph/expand**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EXPAND) })
  );
  await page.route("**/api/audit/**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_AUDIT) })
  );

  await page.goto("/");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${SCREENSHOTS}/task10-03-no-errors.png` });

  const unexpectedErrors = jsErrors.filter(
    (e) => !e.includes("Failed to fetch") && !e.includes("NetworkError")
  );
  expect(unexpectedErrors).toHaveLength(0);
});
