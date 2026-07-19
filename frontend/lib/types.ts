/** Shared API + UI types for the CoGMEM Inspector. */

export interface ApiNode {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
}

export interface ApiRel {
  id: string;
  type: string;
  startNodeId: string;
  endNodeId: string;
  properties: Record<string, unknown>;
}

export interface ApiGraph {
  nodes: ApiNode[];
  relationships: ApiRel[];
}

export interface ToolCall {
  name: string;
  inputs: Record<string, unknown>;
  duration_ms: number;
  output_preview: string;
  error?: string;
}

export interface ChatResult {
  response: string;
  tool_calls: ToolCall[];
  graph_data: ApiGraph;
  session_id: string;
  memory_active?: boolean;
  entities_extracted?: number;
  preferences_detected?: number;
}

export interface ChatTurn {
  role: "user" | "model";
  text: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  toolCalls?: ToolCallState[];
  /** distinct node-label counts from graph_data, e.g. {Requirement: 2} */
  labelCounts?: Record<string, number>;
  /** memory extraction counts from the backend, shown as badges */
  entitiesExtracted?: number;
  preferencesDetected?: number;
  error?: boolean;
  pending?: boolean;
}

export interface TraceStep {
  id: string;
  decision: string;
  content: string | null;
  timestamp: string | null;
}

export interface Trace {
  id: string;
  label: string;
  agent_role: string;
  confidence: number | null;
  reasoning: string | null;
  steps: TraceStep[];
}

export interface Report {
  id: string;
  summary: string;
  coverage_pct: number | null;
  open_findings_count: number | null;
  created_at: string | null;
}

export type ChatStreamEvent =
  | { event: "session_id"; data: { session_id: string } }
  | { event: "tool_start"; data: { name: string; inputs: Record<string, unknown> } }
  | {
      event: "tool_end";
      data: ToolCall & { graph_data: ApiGraph | null };
    }
  | { event: "text_delta"; data: { text: string } }
  | { event: "entities_extracted"; data: { count: number } }
  | { event: "preferences_detected"; data: { count: number } }
  | { event: "error"; data: { detail: string } }
  | { event: "done"; data: Partial<ChatResult> & { session_id: string } };

/** A tool row in the live timeline. */
export interface ToolCallState {
  name: string;
  inputs: Record<string, unknown>;
  status: "running" | "complete" | "error";
  durationMs?: number;
  outputPreview?: string;
}

export interface SelectedNode {
  elementId: string;
  labels: string[];
  logicalId: string;
  properties: Record<string, unknown>;
}
