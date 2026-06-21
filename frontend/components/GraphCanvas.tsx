"use client";

import { useEffect, useState } from "react";
import { InteractiveNvlWrapper } from "@neo4j-nvl/react";
import type { Node, Relationship } from "@neo4j-nvl/base";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getNodeColor(labels: string[]): string {
  const first = labels[0] ?? "";
  if (["Requirement", "AcceptanceCriterion", "Actor"].includes(first)) return "#3B82F6";
  if (first === "Functionality") return "#6366F1";
  if (["Component", "File", "Commit"].includes(first)) return "#22C55E";
  if (["Test", "TestRun", "SecurityFinding", "Report"].includes(first)) return "#F59E0B";
  if (["Judgment", "ReasoningTrace"].includes(first)) return "#A855F7";
  return "#6B7280";
}

interface ApiNode {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
}

interface ApiRel {
  id: string;
  type: string;
  startNodeId: string;
  endNodeId: string;
  properties: Record<string, unknown>;
}

interface Props {
  onNodeClick?: (nodeId: string) => void;
}

export default function GraphCanvas({ onNodeClick }: Props) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [rels, setRels] = useState<Relationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/graph`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<{ nodes: ApiNode[]; relationships: ApiRel[] }>;
      })
      .then((data) => {
        setNodes(
          data.nodes.map((n) => ({
            id: n.id,
            color: getNodeColor(n.labels),
            caption: (n.properties.id as string | undefined) || n.labels[0] || n.id,
          }))
        );
        setRels(
          data.relationships.map((r) => ({
            id: r.id,
            from: r.startNodeId,
            to: r.endNodeId,
            type: r.type,
            caption: r.type,
          }))
        );
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div data-testid="graph-canvas" style={{ height: "100%", width: "100%" }}>
      {loading && (
        <div
          data-testid="graph-loading"
          className="flex h-full items-center justify-center text-gray-400"
        >
          Loading graph…
        </div>
      )}
      {!loading && error && (
        <div
          data-testid="graph-error"
          className="flex h-full items-center justify-center text-red-400"
        >
          Could not connect to backend: {error}
        </div>
      )}
      {!loading && !error && (
        <InteractiveNvlWrapper
          nodes={nodes}
          rels={rels}
          mouseEventCallbacks={{
            onNodeClick: (node) => onNodeClick?.(node.id),
          }}
          nvlOptions={{ allowDynamicMinZoom: true }}
        />
      )}
    </div>
  );
}
