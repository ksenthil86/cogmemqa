/**
 * v7 integration smoke — verifies the three-panel chat inspector.
 * All APIs are mocked so the test requires only the Next.js dev server.
 */
import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

const MOCK_GRAPH = {
  nodes: [
    { id: "n1", labels: ["Requirement"], properties: { id: "req-account-opening", title: "Account Opening" } },
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

const MOCK_TRACES = [
  {
    id: "judgment-1",
    label: "HEALTH_REPORT_GENERATED",
    agent_role: "qa_supervisor",
    confidence: 0.9,
    reasoning: "Coverage complete; 1 open LOW finding.",
    steps: [
      { id: "t1", decision: "Queried coverage", content: "10/10 ACs covered", timestamp: "2026-07-16T00:00:00Z" },
      { id: "t2", decision: "Assessed status", content: "NEEDS REVIEW", timestamp: "2026-07-16T00:00:01Z" },
    ],
  },
];

const MOCK_REPORTS = [
  {
    id: "report-1",
    summary: "All acceptance criteria covered; 1 open LOW security finding.",
    coverage_pct: 100.0,
    open_findings_count: 1,
    created_at: "2026-07-16T00:00:00Z",
  },
];

async function mockApis(page: import("@playwright/test").Page) {
  await page.route("**/api/graph", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/graph/expand**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ nodes: [], relationships: [] }) })
  );
  await page.route("**/api/traces**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_TRACES) })
  );
  await page.route("**/api/reports", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_REPORTS) })
  );
}

test("v7-01 three-panel inspector renders", async ({ page }) => {
  await mockApis(page);

  await page.goto("/");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${SCREENSHOTS}/v7-01-three-panels.png` });

  // Header
  await expect(page.getByTestId("page-title")).toContainText("CoGMEM Inspector");

  // Chat panel
  await expect(page.getByTestId("chat-input")).toBeVisible();
  await expect(page.getByTestId("demo-scenario").first()).toBeVisible();

  // Graph panel — NVL canvas inside the sized container
  await expect(page.getByTestId("main-canvas").getByTestId("nvl-c2d-canvas")).toBeVisible();

  // Decision panel — trace card from mock
  await expect(page.getByTestId("trace-card")).toBeVisible();
  await expect(page.getByTestId("trace-card")).toContainText("Health Report Generated");
});

test("v7-02 documents tab shows health reports", async ({ page }) => {
  await mockApis(page);

  await page.goto("/");
  await page.getByTestId("tab-documents").click();
  await page.screenshot({ path: `${SCREENSHOTS}/v7-02-documents-tab.png` });

  await expect(page.getByTestId("report-card")).toBeVisible();
  await expect(page.getByTestId("report-card")).toContainText("report-1");
});

test("v7-03 no JS errors during dashboard lifecycle", async ({ page }) => {
  const jsErrors: string[] = [];
  page.on("pageerror", (err) => jsErrors.push(err.message));

  await mockApis(page);

  await page.goto("/");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${SCREENSHOTS}/v7-03-no-errors.png` });

  const unexpectedErrors = jsErrors.filter(
    (e) => !e.includes("Failed to fetch") && !e.includes("NetworkError")
  );
  expect(unexpectedErrors).toHaveLength(0);
});
