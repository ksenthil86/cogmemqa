"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { InteractiveNvlWrapper } from "@neo4j-nvl/react";
import type { Node, Relationship } from "@neo4j-nvl/base";
import type { ApiGraph, ApiNode, ApiRel, SelectedNode } from "@/lib/types";
import { API_URL } from "@/lib/api";
import { DEFAULT_NODE_COLOR, FALLBACK_CONFIG, fetchAppConfig } from "@/lib/config";

const SELECTED_COLOR = "#E53E3E";
const EXPANDED_COLOR = "#38A169";
const SELECTED_SIZE = 32;

interface NodeMeta {
  labels: string[];
  logicalId: string;
  properties: Record<string, unknown>;
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
  // Colors come from /api/config (schema/cogmem-qa.yaml); fallback until loaded.
  const colorsRef = useRef<Record<string, string>>(FALLBACK_CONFIG.node_colors);
  const selectedIdRef = useRef<string | null>(null);
  const expandedIdsRef = useRef<Set<string>>(new Set());

  const baseColor = useCallback((id: string): string => {
    const label = nodeMetaRef.current.get(id)?.labels[0] ?? "";
    return colorsRef.current[label] ?? DEFAULT_NODE_COLOR;
  }, []);

  /** Scaffold-style styling: selected red + bigger, expanded green. */
  const styleNode = useCallback(
    (n: Node): Node => {
      if (n.id === selectedIdRef.current) {
        return { ...n, color: SELECTED_COLOR, size: SELECTED_SIZE };
      }
      if (expandedIdsRef.current.has(n.id)) {
        return { ...n, color: EXPANDED_COLOR, size: undefined };
      }
      return { ...n, color: baseColor(n.id), size: undefined };
    },
    [baseColor]
  );

  const toNvlNode = useCallback(
    (n: ApiNode): Node =>
      styleNode({
        id: n.id,
        caption: (n.properties.id as string | undefined) || n.labels[0] || n.id,
      }),
    [styleNode]
  );

  const restyleAll = useCallback(() => {
    setNodes((prev) => prev.map(styleNode));
  }, [styleNode]);

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
    [registerMeta, toNvlNode]
  );

  useEffect(() => {
    // Colors first (cached after first call), then the graph snapshot.
    fetchAppConfig()
      .then((cfg) => {
        colorsRef.current = cfg.node_colors;
      })
      .then(() => fetch(`${API_URL}/api/graph`))
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
  }, [registerMeta, toNvlNode]);

  // Nodes surfaced by chat tool calls flow in through externalGraph.
  useEffect(() => {
    if (externalGraph && externalGraph.nodes.length) {
      mergeGraph(externalGraph);
    }
  }, [externalGraph, mergeGraph]);

  // Single click: select + inspect (no expansion).
  const handleNodeClick = useCallback(
    (clickedId: string) => {
      selectedIdRef.current = clickedId;
      restyleAll();

      const meta = nodeMetaRef.current.get(clickedId);
      onNodeClick?.({
        elementId: clickedId,
        labels: meta?.labels ?? [],
        logicalId: meta?.logicalId ?? clickedId,
        properties: meta?.properties ?? {},
      });
    },
    [onNodeClick, restyleAll]
  );

  // Double click: expand the 1-hop neighbourhood.
  const handleNodeDoubleClick = useCallback(
    (clickedId: string) => {
      expandedIdsRef.current.add(clickedId);
      fetch(`${API_URL}/api/graph/expand?element_id=${encodeURIComponent(clickedId)}`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json() as Promise<ApiGraph>;
        })
        .then((data) => {
          mergeGraph(data);
          restyleAll();
        })
        .catch(() => {
          // Non-fatal — graph stays visible
        });
    },
    [mergeGraph, restyleAll]
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
            onNodeDoubleClick: (node) => handleNodeDoubleClick(node.id),
          }}
          nvlOptions={{
            layout: "d3Force",
            initialZoom: 1,
            minZoom: 0.1,
            maxZoom: 5,
            relationshipThreshold: 0.55,
            allowDynamicMinZoom: true,
            disableTelemetry: true,
          }}
        />
      )}
    </div>
  );
}
