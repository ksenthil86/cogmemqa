"use client";

import { useState } from "react";
import dynamic from "next/dynamic";

const GraphCanvas = dynamic(() => import("@/components/GraphCanvas"), { ssr: false });

export default function Home() {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  return (
    <main className="flex h-screen flex-col bg-gray-950 text-white">
      <header className="flex flex-shrink-0 items-center border-b border-gray-800 px-6 py-3">
        <h1 data-testid="page-title" className="text-xl font-bold text-white">
          CoGMEM Inspector
        </h1>
        {selectedNodeId && (
          <span
            data-testid="selected-node-id"
            className="ml-4 text-sm text-gray-400"
          >
            {selectedNodeId}
          </span>
        )}
      </header>
      <div className="flex-1" style={{ minHeight: 0 }}>
        <GraphCanvas onNodeClick={setSelectedNodeId} />
      </div>
    </main>
  );
}
