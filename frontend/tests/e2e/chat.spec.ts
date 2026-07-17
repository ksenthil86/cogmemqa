/**
 * ChatPanel e2e — POST /api/chat mocked with canned tool calls + graph data.
 */
import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

const MOCK_CHAT_RESULT = {
  response: "Test coverage is 100% (10 of 10 acceptance criteria).",
  tool_calls: [
    { name: "get_health", inputs: {}, duration_ms: 42, output_preview: "{\"coverage_pct\": 100.0}" },
  ],
  graph_data: {
    nodes: [
      { id: "chat-n1", labels: ["Requirement"], properties: { id: "req-account-opening" } },
      { id: "chat-n2", labels: ["Test"], properties: { id: "test-1" } },
    ],
    relationships: [],
  },
};

async function mockApis(page: import("@playwright/test").Page) {
  // Empty initial graph so nodes added by chat are the only ones present.
  await page.route("**/api/graph", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ nodes: [], relationships: [] }) })
  );
  await page.route("**/api/traces**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: "[]" })
  );
  await page.route("**/api/reports", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: "[]" })
  );
}

test("chat-01 send message → tool timeline, answer, badges, graph merge", async ({ page }) => {
  await mockApis(page);
  let chatCalls = 0;
  await page.route("**/api/chat", (r) => {
    chatCalls++;
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_CHAT_RESULT) });
  });

  await page.goto("/");
  await page.getByTestId("chat-input").fill("What is the current test coverage?");
  await page.getByTestId("chat-send").click();

  // user bubble
  await expect(page.getByTestId("chat-message-user")).toContainText("test coverage");

  // assistant answer
  await expect(page.getByTestId("chat-message-assistant")).toContainText("100%");

  // tool timeline
  await expect(page.getByTestId("tool-call-item")).toContainText("get_health");
  await expect(page.getByTestId("tool-call-item")).toContainText("42ms");

  // label badges from graph_data
  await expect(page.getByTestId("chat-badges")).toContainText("Requirement");
  await expect(page.getByTestId("chat-badges")).toContainText("Test");

  await page.screenshot({ path: `${SCREENSHOTS}/chat-01-full-reply.png` });
  expect(chatCalls).toBe(1);
});

test("chat-02 demo scenario button fires a chat request", async ({ page }) => {
  await mockApis(page);
  const bodies: string[] = [];
  await page.route("**/api/chat", async (r) => {
    bodies.push(r.request().postData() ?? "");
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_CHAT_RESULT) });
  });

  await page.goto("/");
  await page.getByTestId("demo-scenario").first().click();

  await expect(page.getByTestId("chat-message-assistant")).toBeVisible();
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toContain("test coverage");
  await page.screenshot({ path: `${SCREENSHOTS}/chat-02-demo-scenario.png` });
});

test("chat-03 backend failure renders error card", async ({ page }) => {
  await mockApis(page);
  await page.route("**/api/chat", (r) =>
    r.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: "chat agent failed" }) })
  );

  await page.goto("/");
  await page.getByTestId("chat-input").fill("hello");
  await page.getByTestId("chat-send").click();

  await expect(page.getByTestId("chat-message-error")).toContainText("chat agent failed");
  await page.screenshot({ path: `${SCREENSHOTS}/chat-03-error-card.png` });
});

test("chat-04 follow-up sends prior turns as history", async ({ page }) => {
  await mockApis(page);
  const bodies: Array<{ message: string; history: Array<{ role: string; text: string }> }> = [];
  await page.route("**/api/chat", async (r) => {
    bodies.push(JSON.parse(r.request().postData() ?? "{}"));
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_CHAT_RESULT) });
  });

  await page.goto("/");
  await page.getByTestId("chat-input").fill("first question");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-message-assistant")).toBeVisible();

  await page.getByTestId("chat-input").fill("follow-up question");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-message-assistant").nth(1)).toBeVisible();

  expect(bodies).toHaveLength(2);
  expect(bodies[0].history).toHaveLength(0);
  expect(bodies[1].history).toHaveLength(2); // user + model from turn 1
  expect(bodies[1].history[0].text).toBe("first question");
});
