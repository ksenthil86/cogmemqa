/**
 * SSE client for POST /api/chat/stream.
 *
 * EventSource can't POST, so this parses the stream manually from
 * fetch + ReadableStream (pattern from the create-context-graph scaffold).
 * The idle timer resets on every received line — the stream aborts only
 * after IDLE_TIMEOUT_MS of *silence*, not total duration.
 */
import { API_URL } from "./api";
import type { ChatStreamEvent } from "./types";

const IDLE_TIMEOUT_MS = 120_000;

export interface StreamChatOptions {
  message: string;
  sessionId: string;
  onEvent: (event: ChatStreamEvent) => void;
  signal?: AbortSignal;
}

export async function streamChat({
  message,
  sessionId,
  onEvent,
  signal,
}: StreamChatOptions): Promise<void> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort);

  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  const resetIdle = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller.abort(), IDLE_TIMEOUT_MS);
  };

  try {
    const res = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        // keep status-code message
      }
      throw new Error(detail);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent: string | null = null;
    resetIdle();

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      resetIdle();

      let newlineIdx: number;
      while ((newlineIdx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newlineIdx).trimEnd();
        buffer = buffer.slice(newlineIdx + 1);
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7);
        } else if (line.startsWith("data: ") && currentEvent) {
          let data: unknown = {};
          try {
            data = JSON.parse(line.slice(6));
          } catch {
            // malformed data line — skip
          }
          onEvent({ event: currentEvent, data } as ChatStreamEvent);
          if (currentEvent === "done") return;
          currentEvent = null;
        }
      }
    }
  } finally {
    if (idleTimer) clearTimeout(idleTimer);
    signal?.removeEventListener("abort", abort);
  }
}
