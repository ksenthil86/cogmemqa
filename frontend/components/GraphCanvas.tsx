"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { InteractiveNvlWrapper } from "@neo4j-nvl/react";
import type { Node, Relationship } from "@neo4j-nvl/base";
import type { ApiGraph, ApiNode, ApiRel, SelectedNode } from "@/lib/types";
import { API_URL } from "@/lib/api";

function getNodeColor(labels: string[]): string {
  const first = labels[0] ?? "";
  if (["Project", "Epic"].includes(first)) return "#F43F5E";
  if (["Requirement", "AcceptanceCriterion", "Actor"].includes(first)) return "#3B82F6";
  if (first === "Functionality") return "#6366F1";
  if (["Component", "File", "Commit"].includes(first)) return "#22C55E";
  if (["Test", "TestRun", "SecurityFinding", "Report"].includes(first)) return "#F59E0B";
  if (["Judgment", "ReasoningTrace"].includes(first)) return "#A855F7";
  return "#6B7280";
}

interface NodeMeta {
  labels: string[];
  logicalId: string;
  properties: Record<string, unknown>;
}

function toNvlNode(n: ApiNode): Node {
  return {
    id: n.id,
    color: getNodeColor(n.labels),
    caption: (n.properties.id as string | undefined) || n.labels[0] || n.id,
  };
}

function toNvlRel(r: ApiRel): Relationship {
  return { id: r.id, from: r.startNodeId, to: r.endNodeId, type: r.type, caption: r.type };
}

interface Props {
  onNodeClick?: (node: SelectedNode) => void;
  /** Graph data pushed from outside (e.g. chat tool results); merged by id. */
  externalGraph?: ApiGraph | null;
}

export default function GraphCanvas({ onNodeClick, externalGraph }: Props) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [rels, setRels] = useState<Relationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Preserve label + logicalId + properties per node for the detail card
  const nodeMetaRef = useRef<Map<string, NodeMeta>>(new Map());

  const registerMeta = useCallback((apiNodes: ApiNode[]) => {
    apiNodes.forEach((n) => {
      nodeMetaRef.current.set(n.id, {
        labels: n.labels,
        logicalId: (n.properties.id as string | undefined) || n.id,
        properties: n.properties,
      });
    });
  }, []);

  // Merge incoming API graph data into NVL state, deduplicating by elementId.
  const mergeGraph = useCallback(
    (data: ApiGraph) => {
      registerMeta(data.nodes);
      setNodes((prev) => {
        const seen = new Set(prev.map((n) => n.id));
        const fresh = data.nodes.filter((n) => !seen.has(n.id)).map(toNvlNode);
        return fresh.length ? [...prev, ...fresh] : prev;
      });
      setRels((prev) => {
        const seen = new Set(prev.map((r) => r.id));
        const fresh = data.relationships.filter((r) => !seen.has(r.id)).map(toNvlRel);
        return fresh.length ? [...prev, ...fresh] : prev;
      });
    },
    [registerMeta]
  );

  useEffect(() => {
    fetch(`${API_URL}/api/graph`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<ApiGraph>;
      })
      .then((data) => {
        registerMeta(data.nodes);
        setNodes(data.nodes.map(toNvlNode));
        setRels(data.relationships.map(toNvlRel));
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [registerMeta]);

  // Nodes surfaced by chat tool calls flow in through externalGraph.
  useEffect(() => {
    if (externalGraph && externalGraph.nodes.length) {
      mergeGraph(externalGraph);
    }
  }, [externalGraph, mergeGraph]);

  const handleNodeClick = useCallback(
    (clickedId: string) => {
      // Highlight clicked node
      setNodes((prev) =>
        prev.map((n) =>
          n.id === clickedId ? { ...n, activated: true } : { ...n, activated: false }
        )
      );

      // Expand neighbourhood — silently ignore expansion failures
      fetch(`${API_URL}/api/graph/expand?element_id=${encodeURIComponent(clickedId)}`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json() as Promise<ApiGraph>;
        })
        .then(mergeGraph)
        .catch(() => {
          // Non-fatal — graph stays visible
        });

      const meta = nodeMetaRef.current.get(clickedId);
      onNodeClick?.({
        elementId: clickedId,
        labels: meta?.labels ?? [],
        logicalId: meta?.logicalId ?? clickedId,
        properties: meta?.properties ?? {},
      });
    },
    [onNodeClick, mergeGraph]
  );

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
            onNodeClick: (node) => handleNodeClick(node.id),
          }}
          nvlOptions={{ allowDynamicMinZoom: true }}
        />
      )}
    </div>
  );
}
