"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface HealthData {
  coverage_pct: number;
  covered_ac: number;
  total_ac: number;
  open_findings_count: number;
  by_severity: { low: number; medium: number; high: number };
  report_count: number;
}

function MetricCard({
  label,
  value,
  sub,
  testId,
}: {
  label: string;
  value: string;
  sub?: string;
  testId?: string;
}) {
  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-gray-700 bg-gray-900 p-3"
    >
      <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg border border-gray-700 bg-gray-900 p-3">
      <div className="h-2 w-16 rounded bg-gray-700" />
      <div className="mt-2 h-5 w-24 rounded bg-gray-700" />
    </div>
  );
}

export default function HealthPanel() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = () => {
    fetch(`${API_URL}/api/health`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<HealthData>;
      })
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, 30_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div data-testid="health-skeleton" className="space-y-2 p-3">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div data-testid="health-error" className="p-3 text-xs text-red-400">
        Health unavailable
      </div>
    );
  }

  const isHealthy = data.coverage_pct >= 100 && data.open_findings_count === 0;
  const sev = data.by_severity;

  return (
    <div data-testid="health-panel" className="space-y-2 p-3">
      <MetricCard
        testId="health-coverage"
        label="Coverage"
        value={`${data.covered_ac}/${data.total_ac} ACs`}
        sub={`${data.coverage_pct.toFixed(1)}%`}
      />
      <MetricCard
        testId="health-findings"
        label="Open Findings"
        value={String(data.open_findings_count)}
        sub={`low ${sev.low} / med ${sev.medium} / high ${sev.high}`}
      />
      <MetricCard
        testId="health-reports"
        label="Reports Generated"
        value={String(data.report_count)}
      />
      <div
        data-testid="health-status"
        className={`rounded-lg border p-3 text-center text-sm font-semibold ${
          isHealthy
            ? "border-green-700 bg-green-950 text-green-400"
            : "border-amber-700 bg-amber-950 text-amber-400"
        }`}
      >
        {isHealthy ? "HEALTHY" : "NEEDS REVIEW"}
      </div>
    </div>
  );
}
