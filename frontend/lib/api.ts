/** Thin fetch wrappers over the CoGMEM Inspector backend. */

import type { ChatResult, ChatTurn, Report, Trace } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function checkOk(res: Response): Promise<Response> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // keep the status-code message
    }
    throw new Error(detail);
  }
  return res;
}

export async function postChat(message: string, history: ChatTurn[]): Promise<ChatResult> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  await checkOk(res);
  return res.json();
}

export async function fetchTraces(): Promise<Trace[]> {
  const res = await fetch(`${API_URL}/api/traces`);
  await checkOk(res);
  return res.json();
}

export async function fetchReports(): Promise<Report[]> {
  const res = await fetch(`${API_URL}/api/reports`);
  await checkOk(res);
  return res.json();
}
