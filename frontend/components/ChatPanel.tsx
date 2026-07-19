"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  Loader2,
  Puzzle,
  Send,
  Settings2,
  Square,
  Wrench,
} from "lucide-react";
import { streamChat } from "@/lib/chatStream";
import { fetchAppConfig, type DemoScenario } from "@/lib/config";
import type { ApiGraph, ChatMessage, ChatStreamEvent } from "@/lib/types";

const SESSION_KEY = "cogmem-chat-session";

/** Session id persisted per browser tab; lazily created (SSR-safe). */
function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

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
              {tc.status === "running" ? (
                <Loader2 size={13} className="flex-shrink-0 animate-spin text-amber-600" />
              ) : tc.status === "error" ? (
                <AlertCircle size={13} className="flex-shrink-0 text-red-500" />
              ) : (
                <CheckCircle2 size={13} className="flex-shrink-0 text-green-600" />
              )}
              <span className="truncate">{tc.name}</span>
            </span>
            {tc.status !== "running" && (
              <span className="flex-shrink-0 text-amber-700">{tc.durationMs}ms</span>
            )}
          </li>
        ))}
        {running && !message.toolCalls?.length && (
          <li className="flex items-center gap-1.5 text-amber-700">
            <Loader2 size={13} className="animate-spin" /> thinking…
          </li>
        )}
      </ul>
    </div>
  );
}

function BadgeRow({ message }: { message: ChatMessage }) {
  const labelEntries = Object.entries(message.labelCounts ?? {});
  const entities = message.entitiesExtracted ?? 0;
  const preferences = message.preferencesDetected ?? 0;
  if (!labelEntries.length && !entities && !preferences) return null;
  return (
    <div data-testid="chat-badges" className="flex flex-wrap gap-2">
      {entities > 0 && (
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
          <BrainCircuit size={13} /> {entities} {entities === 1 ? "entity" : "entities"} extracted
        </span>
      )}
      {preferences > 0 && (
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs font-medium text-orange-700">
          <Settings2 size={13} /> {preferences} {preferences === 1 ? "preference" : "preferences"} detected
        </span>
      )}
      {labelEntries.map(([label, count]) => (
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
  const abortRef = useRef<AbortController | null>(null);
  // Text deltas buffer here and flush to state at most every 50ms.
  const textBufferRef = useRef("");
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);

  useEffect(() => {
    fetchAppConfig().then((cfg) => setScenarios(cfg.demo_scenarios));
  }, []);

  useEffect(() => {
    if (seedPrompt) setInput(seedPrompt);
  }, [seedPrompt]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const patchLast = (patch: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => [...prev.slice(0, -1), patch(prev[prev.length - 1])]);
  };

  const flushText = () => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    const buffered = textBufferRef.current;
    if (buffered) patchLast((m) => ({ ...m, text: m.text + buffered }));
    textBufferRef.current = "";
  };

  const handleEvent = (ev: ChatStreamEvent) => {
    switch (ev.event) {
      case "tool_start":
        patchLast((m) => ({
          ...m,
          toolCalls: [
            ...(m.toolCalls ?? []),
            { name: ev.data.name, inputs: ev.data.inputs, status: "running" as const },
          ],
        }));
        break;
      case "tool_end": {
        if (ev.data.graph_data?.nodes?.length) onGraphData?.(ev.data.graph_data);
        patchLast((m) => {
          const calls = [...(m.toolCalls ?? [])];
          const idx = calls.findIndex(
            (c) => c.status === "running" && c.name === ev.data.name
          );
          if (idx >= 0) {
            calls[idx] = {
              ...calls[idx],
              status: ev.data.error ? "error" : "complete",
              durationMs: ev.data.duration_ms,
              outputPreview: ev.data.output_preview,
            };
          }
          return { ...m, toolCalls: calls };
        });
        break;
      }
      case "text_delta":
        textBufferRef.current += ev.data.text;
        if (!flushTimerRef.current) {
          flushTimerRef.current = setTimeout(flushText, 50);
        }
        break;
      case "entities_extracted":
        patchLast((m) => ({ ...m, entitiesExtracted: ev.data.count }));
        break;
      case "preferences_detected":
        patchLast((m) => ({ ...m, preferencesDetected: ev.data.count }));
        break;
      case "error":
        flushText();
        patchLast((m) => ({ ...m, text: ev.data.detail, error: true, pending: false }));
        break;
      case "done": {
        flushText();
        const graph = ev.data.graph_data;
        if (graph?.nodes?.length) onGraphData?.(graph);
        patchLast((m) => ({
          ...m,
          // The done event carries the authoritative full response.
          text: m.error ? m.text : (ev.data.response ?? m.text),
          pending: false,
          labelCounts: graph ? labelCountsFrom(graph) : m.labelCounts,
        }));
        break;
      }
    }
  };

  const stop = () => abortRef.current?.abort();

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;

    setBusy(true);
    setInput("");
    textBufferRef.current = "";
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: "", pending: true, toolCalls: [] },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat({
        message: question,
        sessionId: getSessionId(),
        onEvent: handleEvent,
        signal: controller.signal,
      });
      onDone?.();
    } catch (err) {
      flushText();
      const aborted = err instanceof DOMException && err.name === "AbortError";
      patchLast((m) => ({
        ...m,
        text: aborted
          ? m.text || "(stopped)"
          : err instanceof Error
            ? err.message
            : String(err),
        error: !aborted,
        pending: false,
      }));
    } finally {
      setBusy(false);
      abortRef.current = null;
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
              {m.pending && !m.text ? (
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
              {!m.pending && !m.error && <BadgeRow message={m} />}
            </div>
          )
        )}

        {scenarios.length > 0 && (
          <div>
            <p className="mb-2 text-xs text-gray-500">Try a demo scenario:</p>
            <div className="grid grid-cols-2 gap-2">
              {scenarios.map((s) => (
                <button
                  key={s.name}
                  data-testid="demo-scenario"
                  disabled={busy}
                  onClick={() => send(s.prompts[0])}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 transition hover:border-gray-400 hover:bg-gray-50 disabled:opacity-50"
                >
                  {s.name}
                </button>
              ))}
            </div>
          </div>
        )}
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
          {busy ? (
            <button
              data-testid="chat-stop"
              type="button"
              onClick={stop}
              className="flex-shrink-0 rounded-lg bg-red-500 p-1.5 text-white transition hover:bg-red-600"
            >
              <Square size={15} />
            </button>
          ) : (
            <button
              data-testid="chat-send"
              type="submit"
              disabled={!input.trim()}
              className="flex-shrink-0 rounded-lg bg-blue-500 p-1.5 text-white transition hover:bg-blue-600 disabled:opacity-50"
            >
              <Send size={15} />
            </button>
          )}
        </form>
      </div>
    </section>
  );
}
