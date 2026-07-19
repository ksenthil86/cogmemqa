/**
 * ChatPanel e2e — POST /api/chat/stream mocked with a canned SSE body.
 */
import { test, expect } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "../../../tests/screenshots");

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

const GRAPH_DATA = {
  nodes: [
    { id: "chat-n1", labels: ["Requirement"], properties: { id: "req-account-opening" } },
    { id: "chat-n2", labels: ["Test"], properties: { id: "test-1" } },
  ],
  relationships: [],
};

const DONE_PAYLOAD = {
  response: "Test coverage is 100% (10 of 10 acceptance criteria).",
  tool_calls: [
    { name: "get_health", inputs: {}, duration_ms: 42, output_preview: "{\"coverage_pct\": 100.0}" },
  ],
  graph_data: GRAPH_DATA,
  session_id: "e2e-session",
  memory_active: true,
  entities_extracted: 2,
  preferences_detected: 1,
};

const MOCK_SSE_BODY =
  sse("session_id", { session_id: "e2e-session" }) +
  sse("entities_extracted", { count: 2 }) +
  sse("preferences_detected", { count: 1 }) +
  sse("tool_start", { name: "get_health", inputs: {} }) +
  sse("tool_end", {
    name: "get_health", inputs: {}, duration_ms: 42,
    output_preview: "{\"coverage_pct\": 100.0}", graph_data: GRAPH_DATA,
  }) +
  sse("text_delta", { text: "Test coverage is 100% " }) +
  sse("text_delta", { text: "(10 of 10 acceptance criteria)." }) +
  sse("done", DONE_PAYLOAD);

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
  await page.route("**/api/config", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        node_colors: {},
        node_sizes: {},
        demo_scenarios: [
          { name: "Coverage & Quality", prompts: ["What is the current test coverage?"] },
        ],
      }),
    })
  );
}

function mockChatStream(page: import("@playwright/test").Page, bodies?: string[]) {
  return page.route("**/api/chat/stream", async (r) => {
    bodies?.push(r.request().postData() ?? "");
    return r.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: MOCK_SSE_BODY,
    });
  });
}

test("chat-01 send message → tool timeline, answer, badges, graph merge", async ({ page }) => {
  await mockApis(page);
  const bodies: string[] = [];
  await mockChatStream(page, bodies);

  await page.goto("/");
  await page.getByTestId("chat-input").fill("What is the current test coverage?");
  await page.getByTestId("chat-send").click();

  await expect(page.getByTestId("chat-message-user")).toContainText("test coverage");
  await expect(page.getByTestId("chat-message-assistant")).toContainText("100%");

  await expect(page.getByTestId("tool-call-item")).toContainText("get_health");
  await expect(page.getByTestId("tool-call-item")).toContainText("42ms");

  await expect(page.getByTestId("chat-badges")).toContainText("Requirement");
  await expect(page.getByTestId("chat-badges")).toContainText("2 entities extracted");
  await expect(page.getByTestId("chat-badges")).toContainText("1 preference detected");

  await page.screenshot({ path: `${SCREENSHOTS}/chat-01-full-reply.png` });
  expect(bodies).toHaveLength(1);
});

test("chat-02 demo scenario button fires a chat request", async ({ page }) => {
  await mockApis(page);
  const bodies: string[] = [];
  await mockChatStream(page, bodies);

  await page.goto("/");
  await page.getByTestId("demo-scenario").first().click();

  await expect(page.getByTestId("chat-message-assistant")).toBeVisible();
  expect(bodies).toHaveLength(1);
});

test("chat-03 backend failure renders error card", async ({ page }) => {
  await mockApis(page);
  await page.route("**/api/chat/stream", (r) =>
    r.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: "chat agent failed" }) })
  );

  await page.goto("/");
  await page.getByTestId("chat-input").fill("hello");
  await page.getByTestId("chat-send").click();

  await expect(page.getByTestId("chat-message-error")).toContainText("chat agent failed");
  await page.screenshot({ path: `${SCREENSHOTS}/chat-03-error-card.png` });
});

test("chat-04 turns share a persisted session_id, no client history", async ({ page }) => {
  await mockApis(page);
  const bodies: string[] = [];
  await mockChatStream(page, bodies);

  await page.goto("/");
  await page.getByTestId("chat-input").fill("first question");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-message-assistant")).toBeVisible();

  await page.getByTestId("chat-input").fill("follow-up question");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-message-assistant").nth(1)).toBeVisible();

  expect(bodies).toHaveLength(2);
  const first = JSON.parse(bodies[0]);
  const second = JSON.parse(bodies[1]);
  expect(first.history).toBeUndefined();
  expect(second.history).toBeUndefined();
  expect(first.session_id).toBeTruthy();
  expect(second.session_id).toBe(first.session_id);
});

test("chat-05 stream error event renders error card", async ({ page }) => {
  await mockApis(page);
  await page.route("**/api/chat/stream", (r) =>
    r.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body:
        sse("session_id", { session_id: "e2e-err" }) +
        sse("error", { detail: "agent exploded mid-flight" }) +
        sse("done", { session_id: "e2e-err" }),
    })
  );

  await page.goto("/");
  await page.getByTestId("chat-input").fill("hello");
  await page.getByTestId("chat-send").click();

  await expect(page.getByTestId("chat-message-error")).toContainText("agent exploded mid-flight");
});
