"use client";

import { useSearchParams } from "next/navigation";
import AuditPanel from "@/components/AuditPanel";

export default function AuditTestClient() {
  const params = useSearchParams();
  const reqId = params.get("reqId");
  return (
    <div className="bg-gray-950 min-h-screen p-4 text-white">
      <AuditPanel reqId={reqId} />
    </div>
  );
}
