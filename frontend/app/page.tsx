"use client";

import { useCallback, useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import ContextGraphPanel from "@/components/ContextGraphPanel";
import DecisionPanel from "@/components/DecisionPanel";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { ApiGraph, SelectedNode } from "@/lib/types";

export default function Home() {
  // Graph data surfaced by chat tool calls, merged and pushed to the canvas.
  const [chatGraph, setChatGraph] = useState<ApiGraph | null>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [seedPrompt, setSeedPrompt] = useState("");
  // Bumped after each chat reply so DecisionPanel refetches traces.
  const [tracesVersion, setTracesVersion] = useState(0);

  const handleGraphData = useCallback((graph: ApiGraph) => {
    // Replace the reference so GraphCanvas's merge effect fires; GraphCanvas
    // deduplicates by elementId, so repeated nodes are harmless.
    setChatGraph(graph);
  }, []);

  const handleAskAbout = useCallback((node: SelectedNode) => {
    setSeedPrompt(`Tell me about ${node.logicalId} (${node.labels[0] ?? "node"})`);
  }, []);

  return (
    <main className="flex h-screen flex-col bg-gray-100 text-gray-900">
      {/* browser-chrome style title bar */}
      <header className="flex flex-shrink-0 items-center border-b border-gray-200 bg-gray-50 px-4 py-2.5">
        <div className="flex gap-2">
          <span className="h-3 w-3 rounded-full bg-red-400" />
          <span className="h-3 w-3 rounded-full bg-yellow-400" />
          <span className="h-3 w-3 rounded-full bg-green-400" />
        </div>
        <h1
          data-testid="page-title"
          className="flex-1 text-center font-mono text-sm text-gray-500"
        >
          localhost:3000 — CoGMEM Inspector
        </h1>
        <div className="w-[52px]" />
      </header>

      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        <ErrorBoundary label="Chat panel">
          <ChatPanel
            seedPrompt={seedPrompt}
            onGraphData={handleGraphData}
            onDone={() => setTracesVersion((v) => v + 1)}
          />
        </ErrorBoundary>
        <ErrorBoundary label="Context graph">
          <ContextGraphPanel
            externalGraph={chatGraph}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            onAskAbout={handleAskAbout}
          />
        </ErrorBoundary>
        <ErrorBoundary label="Decision panel">
          <DecisionPanel refreshKey={tracesVersion} />
        </ErrorBoundary>
      </div>
    </main>
  );
}
