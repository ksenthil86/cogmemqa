import { Suspense } from "react";
import AuditTestClient from "./client";

export default function AuditTestPage() {
  return (
    <Suspense>
      <AuditTestClient />
    </Suspense>
  );
}
