"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { FALLBACK_CONFIG, fetchAppConfig } from "@/lib/config";
import type { ApiGraph, SelectedNode } from "@/lib/types";

const GraphCanvas = dynamic(() => import("@/components/GraphCanvas"), { ssr: false });

/** Legend layers with a representative label whose color comes from /api/config. */
const LAYER_REPS: Array<[layer: string, representative: string]> = [
  ["Portfolio", "Project"],
  ["Requirements", "Requirement"],
  ["Capability", "Functionality"],
  ["Implementation", "File"],
  ["Evidence", "Test"],
  ["Reasoning", "Judgment"],
];

/** Properties worth surfacing in the detail card, in preference order. */
const DETAIL_KEYS = [
  "title", "name", "statement", "path", "sha", "message",
  "severity", "status", "priority", "outcome", "summary", "agent_role", "label",
];

interface Props {
  externalGraph?: ApiGraph | null;
  selectedNode: SelectedNode | null;
  onSelectNode: (node: SelectedNode) => void;
  onAskAbout: (node: SelectedNode) => void;
}

export default function ContextGraphPanel({
  externalGraph,
  selectedNode,
  onSelectNode,
  onAskAbout,
}: Props) {
  const [nodeColors, setNodeColors] = useState<Record<string, string>>(
    FALLBACK_CONFIG.node_colors
  );

  useEffect(() => {
    fetchAppConfig().then((cfg) => setNodeColors(cfg.node_colors));
  }, []);

  const detailEntries = selectedNode
    ? DETAIL_KEYS.filter((k) => selectedNode.properties[k] != null)
        .slice(0, 4)
        .map((k) => [k, String(selectedNode.properties[k])] as const)
    : [];

  return (
    <section className="flex min-w-0 flex-1 flex-col border-r border-gray-200 bg-white">
      <div className="flex flex-shrink-0 items-center border-b border-gray-200 bg-green-100 px-5 py-3 text-sm font-semibold text-green-900">
        <span className="mx-auto">Context Graph · NVL Visualization</span>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        {/* graph area — NVL needs a sized parent */}
        <div
          data-testid="main-canvas"
          className="relative min-h-[360px] flex-1 overflow-hidden rounded-xl border border-gray-200 bg-gray-50"
        >
          <GraphCanvas externalGraph={externalGraph} onNodeClick={onSelectNode} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          {/* layer legend */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 text-sm">
            <ul className="space-y-2">
              {LAYER_REPS.map(([layer, rep]) => (
                <li key={layer} className="flex items-center gap-2 text-gray-700">
                  <span
                    className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-full"
                    style={{ background: nodeColors[rep] ?? "#6B7280" }}
                  />
                  {layer}
                </li>
              ))}
            </ul>
          </div>

          {/* node detail card */}
          <div
            data-testid="node-detail"
            className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700"
          >
            {selectedNode ? (
              <>
                <p className="break-all font-semibold text-gray-900">
                  {selectedNode.logicalId}
                </p>
                <dl className="mt-1 space-y-0.5">
                  <div className="flex gap-1">
                    <dt className="text-gray-500">Label:</dt>
                    <dd>{selectedNode.labels[0] ?? "—"}</dd>
                  </div>
                  {detailEntries.map(([k, v]) => (
                    <div key={k} className="flex gap-1">
                      <dt className="flex-shrink-0 text-gray-500">{k}:</dt>
                      <dd className="truncate">{v}</dd>
                    </div>
                  ))}
                </dl>
                <button
                  data-testid="ask-about-node"
                  onClick={() => onAskAbout(selectedNode)}
                  className="mt-2 flex items-center gap-1 text-xs font-medium text-blue-600 hover:underline"
                >
                  ▶ Ask about this
                </button>
              </>
            ) : (
              <p className="text-gray-400">Click a node to inspect it.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
