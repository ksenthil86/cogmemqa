"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Puzzle,
  Send,
  Wrench,
} from "lucide-react";
import { postChat } from "@/lib/api";
import { DEMO_SCENARIOS } from "@/lib/scenarios";
import type { ApiGraph, ChatMessage, ChatTurn } from "@/lib/types";

interface Props {
  /** Text injected into the composer (e.g. "Ask about this" from the graph). */
  seedPrompt?: string;
  /** Called with each reply's graph_data so the graph panel can merge it. */
  onGraphData?: (graph: ApiGraph) => void;
  /** Called after each completed reply (refresh traces, etc.). */
  onDone?: () => void;
}

function labelCountsFrom(graph: ApiGraph): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const node of graph.nodes) {
    const label = node.labels[0] ?? "Node";
    counts[label] = (counts[label] ?? 0) + 1;
  }
  return counts;
}

function ToolCallCard({ message }: { message: ChatMessage }) {
  const running = message.pending;
  if (!running && !message.toolCalls?.length) return null;
  return (
    <div
      data-testid="tool-call-card"
      className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm"
    >
      <div className="mb-2 flex items-center gap-2 font-semibold text-amber-900">
        <Wrench size={15} /> Tool Calls
      </div>
      <ul className="space-y-1 font-mono text-xs text-amber-900/90">
        {message.toolCalls?.map((tc, i) => (
          <li
            key={`${tc.name}-${i}`}
            data-testid="tool-call-item"
            className="flex items-center justify-between gap-2"
          >
            <span className="flex min-w-0 items-center gap-1.5">
              {tc.error ? (
                <AlertCircle size={13} className="flex-shrink-0 text-red-500" />
              ) : (
                <CheckCircle2 size={13} className="flex-shrink-0 text-green-600" />
              )}
              <span className="truncate">{tc.name}</span>
            </span>
            <span className="flex-shrink-0 text-amber-700">{tc.duration_ms}ms</span>
          </li>
        ))}
        {running && (
          <li className="flex items-center gap-1.5 text-amber-700">
            <Loader2 size={13} className="animate-spin" /> querying the graph…
          </li>
        )}
      </ul>
    </div>
  );
}

function LabelChips({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (!entries.length) return null;
  return (
    <div data-testid="chat-badges" className="flex flex-wrap gap-2">
      {entries.map(([label, count]) => (
        <span
          key={label}
          className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700"
        >
          <Puzzle size={13} /> {label} ×{count}
        </span>
      ))}
    </div>
  );
}

export default function ChatPanel({ seedPrompt, onGraphData, onDone }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (seedPrompt) setInput(seedPrompt);
  }, [seedPrompt]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;

    // Client-held history: prior completed turns only.
    const history: ChatTurn[] = messages
      .filter((m) => !m.error && !m.pending)
      .map((m) => ({ role: m.role === "user" ? "user" : "model", text: m.text }));

    setBusy(true);
    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: "", pending: true, toolCalls: [] },
    ]);

    try {
      const result = await postChat(question, history);
      if (result.graph_data.nodes.length) onGraphData?.(result.graph_data);
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          role: "assistant",
          text: result.response,
          toolCalls: result.tool_calls,
          labelCounts: labelCountsFrom(result.graph_data),
        },
      ]);
      onDone?.();
    } catch (err) {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          role: "assistant",
          text: err instanceof Error ? err.message : String(err),
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex min-w-0 flex-1 flex-col border-r border-gray-200 bg-white">
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-gray-200 bg-blue-100 px-5 py-3 text-sm font-semibold text-blue-900">
        <span aria-hidden>🧠</span>
        <span>Chat · CoGMEM-QA</span>
      </div>

      <div ref={scrollRef} className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-gray-500">
            Ask about requirements, test coverage, security findings, or agent
            decisions in the Meridian Bank QA graph.
          </p>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div
                data-testid="chat-message-user"
                className="max-w-[80%] rounded-2xl rounded-br-sm bg-blue-500 px-4 py-2 text-sm font-medium text-white shadow-sm"
              >
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex flex-col gap-2">
              <ToolCallCard message={m} />
              {m.pending ? (
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <Loader2 size={15} className="animate-spin" /> thinking…
                </div>
              ) : m.error ? (
                <div
                  data-testid="chat-message-error"
                  className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
                >
                  Request failed: {m.text}
                </div>
              ) : (
                <div
                  data-testid="chat-message-assistant"
                  className="whitespace-pre-wrap rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-gray-800"
                >
                  {m.text}
                </div>
              )}
              {m.labelCounts && <LabelChips counts={m.labelCounts} />}
            </div>
          )
        )}

        <div>
          <p className="mb-2 text-xs text-gray-500">Try a demo scenario:</p>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_SCENARIOS.map((s) => (
              <button
                key={s.label}
                data-testid="demo-scenario"
                disabled={busy}
                onClick={() => send(s.question)}
                className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 transition hover:border-gray-400 hover:bg-gray-50 disabled:opacity-50"
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-shrink-0 border-t border-gray-200 p-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-3 py-2"
        >
          <input
            data-testid="chat-input"
            type="text"
            value={input}
            disabled={busy}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the knowledge graph..."
            className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm text-gray-800 placeholder:text-gray-400 focus:ring-0 disabled:opacity-50"
          />
          <button
            data-testid="chat-send"
            type="submit"
            disabled={busy || !input.trim()}
            className="flex-shrink-0 rounded-lg bg-blue-500 p-1.5 text-white transition hover:bg-blue-600 disabled:opacity-50"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </form>
      </div>
    </section>
  );
}
