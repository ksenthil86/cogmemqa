"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart3, CheckCircle2, Eye, Square, Wrench } from "lucide-react";
import { fetchReports, fetchTraces } from "@/lib/api";
import type { Report, Trace } from "@/lib/types";

function humanize(label: string | null): string {
  if (!label) return "Decision";
  return label
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function TraceCard({ trace }: { trace: Trace }) {
  const confidence = trace.confidence;
  const confident = confidence == null || confidence >= 0.8;
  return (
    <div data-testid="trace-card" className="rounded-xl border border-gray-200 bg-white p-4">
      <p className="text-sm font-semibold text-gray-900">{humanize(trace.label)}</p>
      <p className="mb-3 text-xs text-gray-500">{trace.agent_role}</p>

      <div className="space-y-3">
        {trace.steps.map((step, i) => (
          <div key={step.id ?? i} className="flex gap-2">
            <span className="text-sm font-semibold text-gray-500">{i + 1}.</span>
            <div className="min-w-0 text-sm">
              <div className="flex items-center gap-1.5 font-medium text-gray-800">
                <Square size={13} className="flex-shrink-0 text-gray-400" />
                <span className="truncate">{step.decision || "step"}</span>
              </div>
              {step.content && (
                <div className="ml-0.5 mt-0.5 flex items-start gap-1.5 text-xs text-gray-600">
                  <Eye size={12} className="mt-0.5 flex-shrink-0 text-gray-400" />
                  <span>{step.content}</span>
                </div>
              )}
            </div>
          </div>
        ))}
        {trace.steps.length === 0 && (
          <p className="text-xs text-gray-400">No recorded steps.</p>
        )}
      </div>

      {trace.reasoning && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs font-medium ${
            confident
              ? "border-green-200 bg-green-50 text-green-800"
              : "border-amber-200 bg-amber-50 text-amber-800"
          }`}
        >
          <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0" />
          <span>
            {trace.reasoning}
            {confidence != null && ` · confidence ${confidence}`}
          </span>
        </div>
      )}
    </div>
  );
}

function ReportCard({ report }: { report: Report }) {
  return (
    <div data-testid="report-card" className="rounded-xl border border-gray-200 bg-white p-3 text-sm">
      <div className="flex items-center gap-1.5 font-medium text-gray-800">
        <BarChart3 size={14} className="flex-shrink-0 text-gray-500" />
        <span className="truncate">Health Report — {report.id}</span>
      </div>
      <p className="mt-0.5 text-xs text-gray-600">{report.summary}</p>
      <p className="mt-0.5 text-xs text-gray-500">
        {report.coverage_pct != null && `coverage ${report.coverage_pct}%`}
        {report.open_findings_count != null && ` · ${report.open_findings_count} open findings`}
        {report.created_at && ` · ${report.created_at.slice(0, 10)}`}
      </p>
    </div>
  );
}

interface Props {
  /** Bump to refetch traces (e.g. after each chat reply). */
  refreshKey?: number;
}

export default function DecisionPanel({ refreshKey = 0 }: Props) {
  const [tab, setTab] = useState<"traces" | "documents">("traces");
  const [traces, setTraces] = useState<Trace[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState<string | null>(null);

  useEffect(() => {
    fetchTraces()
      .then((data) => {
        setTraces(data);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [refreshKey]);

  useEffect(() => {
    fetchReports().then(setReports).catch(() => {
      // reports tab shows its own empty state
    });
  }, [refreshKey]);

  const roleCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of traces) counts[t.agent_role] = (counts[t.agent_role] ?? 0) + 1;
    return counts;
  }, [traces]);

  const visibleTraces = roleFilter
    ? traces.filter((t) => t.agent_role === roleFilter)
    : traces;

  return (
    <section className="flex w-[360px] flex-shrink-0 flex-col bg-white">
      <div className="flex flex-shrink-0 border-b border-gray-200">
        <button
          data-testid="tab-traces"
          onClick={() => setTab("traces")}
          className={`px-5 py-3 text-sm font-semibold ${
            tab === "traces"
              ? "bg-purple-100 text-purple-900"
              : "text-gray-400 hover:text-gray-600"
          }`}
        >
          Decision Traces
        </button>
        <button
          data-testid="tab-documents"
          onClick={() => setTab("documents")}
          className={`px-5 py-3 text-sm font-semibold ${
            tab === "documents"
              ? "bg-purple-100 text-purple-900"
              : "text-gray-400 hover:text-gray-600"
          }`}
        >
          Documents
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
        {tab === "traces" ? (
          <>
            {error && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                Could not load traces: {error}
              </div>
            )}
            {!error && traces.length === 0 && (
              <p className="text-sm text-gray-400">No decision traces recorded yet.</p>
            )}

            {Object.keys(roleCounts).length > 1 && (
              <div>
                <p className="mb-2 text-xs text-gray-500">Filter by agent:</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(roleCounts).map(([role, count]) => (
                    <button
                      key={role}
                      data-testid="trace-filter"
                      onClick={() => setRoleFilter(roleFilter === role ? null : role)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                        roleFilter === role
                          ? "border-blue-300 bg-blue-50 text-blue-700"
                          : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
                      }`}
                    >
                      {role} ({count})
                    </button>
                  ))}
                </div>
              </div>
            )}

            {visibleTraces.slice(0, 20).map((t) => (
              <TraceCard key={t.id} trace={t} />
            ))}
          </>
        ) : (
          <>
            {reports.length === 0 && (
              <p className="text-sm text-gray-400">No health reports yet.</p>
            )}
            {reports.map((r) => (
              <ReportCard key={r.id} report={r} />
            ))}
          </>
        )}
      </div>
    </section>
  );
}
