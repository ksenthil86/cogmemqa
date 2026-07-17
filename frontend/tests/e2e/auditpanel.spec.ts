import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

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

const MOCK_EMPTY_AUDIT = { req_id: "req-unknown", chain: [] };

const MOCK_GRAPH = {
  nodes: [
    { id: "node-1", labels: ["Requirement"], properties: { id: "req-account-opening" } },
    { id: "node-2", labels: ["Functionality"], properties: { id: "func-account-opening" } },
  ],
  relationships: [
    { id: "rel-1", type: "REALIZED_BY", startNodeId: "node-1", endNodeId: "node-2", properties: {} },
  ],
};

// ── AuditPanel isolated tests ─────────────────────────────────────────────────

test("task9-01 AuditPanel shows select prompt when reqId is null", async ({ page }) => {
  await page.goto("/audit-test");
  await page.screenshot({ path: `${SCREENSHOTS}/task9-01-audit-empty.png` });
  await expect(page.getByTestId("audit-empty")).toBeVisible();
  await expect(page.getByTestId("audit-empty")).toContainText("select a Requirement node");
});

test("task9-02 AuditPanel renders chain when reqId is provided", async ({ page }) => {
  await page.route("**/api/audit/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_AUDIT) })
  );

  await page.goto("/audit-test?reqId=req-account-opening");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task9-02-audit-chain.png` });

  await expect(page.getByTestId("audit-panel")).toBeVisible();
  await expect(page.getByTestId("audit-chain-item").first()).toBeVisible();
});

test("task9-03 AuditPanel shows no-chain message when chain is empty", async ({ page }) => {
  await page.route("**/api/audit/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EMPTY_AUDIT),
    })
  );

  await page.goto("/audit-test?reqId=req-unknown");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task9-03-audit-no-chain.png` });

  await expect(page.getByTestId("audit-no-chain")).toBeVisible();
  await expect(page.getByTestId("audit-no-chain")).toContainText("no chain found");
});

test("task9-04 chain item shows req, func, comp, file and commit", async ({ page }) => {
  await page.route("**/api/audit/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_AUDIT) })
  );

  await page.goto("/audit-test?reqId=req-account-opening");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SCREENSHOTS}/task9-04-chain-detail.png` });

  const item = page.getByTestId("audit-chain-item").first();
  await expect(item).toContainText("req-account-opening");
  await expect(item).toContainText("Account Opening");
  await expect(item).toContainText("func-account-opening");
  await expect(item).toContainText("comp-account-opening");
  await expect(item).toContainText("src/account/AccountController.java");
  await expect(item).toContainText("b800001");
});

test("task9-05 AuditPanel shows error state when API fails", async ({ page }) => {
  await page.route("**/api/audit/**", (route) => route.abort());

  await page.goto("/audit-test?reqId=req-account-opening");
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${SCREENSHOTS}/task9-05-audit-error.png` });

  await expect(page.getByTestId("audit-error")).toBeVisible();
});

// ── Page layout test (v7 three-panel layout) ──────────────────────────────────

test("task9-09 GraphCanvas NVL canvas is inside main-canvas area", async ({ page }) => {
  await page.route("**/api/graph", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_GRAPH) })
  );
  await page.route("**/api/traces", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
  );
  await page.route("**/api/reports", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
  );

  await page.goto("/");
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${SCREENSHOTS}/task9-09-canvas-in-main.png` });

  const nvlInMain = page.getByTestId("main-canvas").getByTestId("nvl-c2d-canvas");
  await expect(nvlInMain).toBeVisible();
});
