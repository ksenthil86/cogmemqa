"use client";

import dynamic from "next/dynamic";

const GraphCanvas = dynamic(() => import("@/components/GraphCanvas"), { ssr: false });

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col bg-gray-950 text-white">
      <header className="flex items-center border-b border-gray-800 px-6 py-3">
        <h1 data-testid="page-title" className="text-xl font-bold text-white">
          CoGMEM Inspector
        </h1>
      </header>
      <div className="flex-1" style={{ minHeight: 0 }}>
        <GraphCanvas />
      </div>
    </main>
  );
}
