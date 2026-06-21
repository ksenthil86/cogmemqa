"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ChainItem {
  req: string;
  req_title: string;
  func: string;
  comp: string;
  file: string;
  commit_sha: string | null;
}

interface AuditResponse {
  req_id: string;
  chain: ChainItem[];
}

interface Props {
  reqId: string | null;
}

export default function AuditPanel({ reqId }: Props) {
  const [data, setData] = useState<AuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reqId) {
      setData(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`${API_URL}/api/audit/${encodeURIComponent(reqId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<AuditResponse>;
      })
      .then(setData)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [reqId]);

  if (!reqId) {
    return (
      <div data-testid="audit-empty" className="p-3 text-xs text-gray-500 italic">
        (select a Requirement node)
      </div>
    );
  }

  if (loading) {
    return (
      <div data-testid="audit-loading" className="p-3 text-xs text-gray-400">
        Loading audit trail…
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="audit-error" className="p-3 text-xs text-red-400">
        Audit unavailable
      </div>
    );
  }

  if (!data || data.chain.length === 0) {
    return (
      <div data-testid="audit-no-chain" className="p-3 text-xs text-gray-500 italic">
        (no chain found)
      </div>
    );
  }

  return (
    <div data-testid="audit-panel" className="space-y-3 p-3">
      {data.chain.map((item, i) => (
        <div
          key={i}
          data-testid="audit-chain-item"
          className="rounded border border-gray-700 bg-gray-900 p-2 font-mono text-xs text-gray-300"
        >
          <div className="font-semibold text-blue-400">
            {item.req}{" "}
            <span className="text-gray-400">({item.req_title})</span>
          </div>
          <div className="mt-1 space-y-0.5 pl-2 text-gray-400">
            <div>→ {item.func}</div>
            <div>→ {item.comp}</div>
            <div>→ {item.file}</div>
            {item.commit_sha && <div>← Commit {item.commit_sha}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
