/**
 * Presentation config fetched from GET /api/config, which serves it from
 * schema/cogmem-qa.yaml — the single source of truth for node colors, sizes,
 * and demo scenarios. Falls back to a baked-in copy if the backend is down.
 */
import { API_URL } from "./api";

export interface DemoScenario {
  name: string;
  prompts: string[];
}

export interface AppConfig {
  node_colors: Record<string, string>;
  node_sizes: Record<string, number>;
  demo_scenarios: DemoScenario[];
}

export const FALLBACK_CONFIG: AppConfig = {
  node_colors: {
    Project: "#F43F5E",
    Epic: "#F43F5E",
    Requirement: "#2563EB",
    AcceptanceCriterion: "#2563EB",
    Actor: "#2563EB",
    Functionality: "#6366F1",
    Component: "#6366F1",
    File: "#16A34A",
    Commit: "#16A34A",
    Test: "#F59E0B",
    TestRun: "#F59E0B",
    SecurityFinding: "#F59E0B",
    Report: "#F59E0B",
    Judgment: "#9333EA",
    ReasoningTrace: "#9333EA",
  },
  node_sizes: {},
  demo_scenarios: [
    { name: "Portfolio & Requirements", prompts: ["How is the Meridian project structured into epics?"] },
    { name: "Coverage & Quality", prompts: ["What is the current test coverage?"] },
    { name: "Security & Audit", prompts: ["Are there any open security findings on high-priority requirements?"] },
  ],
};

export const DEFAULT_NODE_COLOR = "#6B7280";

let cached: AppConfig | null = null;
let inflight: Promise<AppConfig> | null = null;

export function fetchAppConfig(): Promise<AppConfig> {
  if (cached) return Promise.resolve(cached);
  if (!inflight) {
    inflight = fetch(`${API_URL}/api/config`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Partial<AppConfig>>;
      })
      .then((cfg) => {
        cached = {
          node_colors: { ...FALLBACK_CONFIG.node_colors, ...cfg.node_colors },
          node_sizes: { ...FALLBACK_CONFIG.node_sizes, ...cfg.node_sizes },
          demo_scenarios: cfg.demo_scenarios?.length
            ? cfg.demo_scenarios
            : FALLBACK_CONFIG.demo_scenarios,
        };
        return cached;
      })
      .catch(() => {
        cached = FALLBACK_CONFIG;
        return cached;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}
