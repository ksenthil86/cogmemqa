"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import HealthPanel from "@/components/HealthPanel";
import AuditPanel from "@/components/AuditPanel";

const GraphCanvas = dynamic(() => import("@/components/GraphCanvas"), { ssr: false });

export default function Home() {
  const [selectedReqId, setSelectedReqId] = useState<string | null>(null);

  const handleNodeClick = (
    _nodeId: string,
    labels: string[],
    logicalId: string
  ) => {
    if (labels[0] === "Requirement") {
      setSelectedReqId(logicalId);
    }
  };

  return (
    <main className="flex h-screen flex-col bg-gray-950 text-white">
      <header className="flex flex-shrink-0 items-center border-b border-gray-800 px-6 py-3">
        <h1 data-testid="page-title" className="text-xl font-bold text-white">
          CoGMEM Inspector
        </h1>
      </header>

      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        {/* Left sidebar — 280 px */}
        <aside
          data-testid="sidebar"
          className="flex flex-shrink-0 flex-col overflow-y-auto border-r border-gray-800"
          style={{ width: "280px" }}
        >
          <HealthPanel />
          <div className="border-t border-gray-800" />
          <div className="px-3 pt-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            Audit Trail
          </div>
          <AuditPanel reqId={selectedReqId} />
        </aside>

        {/* Main canvas area */}
        <div
          data-testid="main-canvas"
          className="flex-1"
          style={{ minWidth: 0 }}
        >
          <GraphCanvas onNodeClick={handleNodeClick} />
        </div>
      </div>
    </main>
  );
}
