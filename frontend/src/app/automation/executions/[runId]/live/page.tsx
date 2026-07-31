"use client";

/**
 * UI-046 route — `/automation/executions/{runId}/live`, exactly as the approved
 * contract specifies.
 *
 * Nested under `/automation` so it inherits that segment's existing shell
 * (`app/automation/layout.tsx`) rather than creating a duplicate top-level page,
 * which delivery rule 5 forbids. The screen is reached from a published suite's
 * Executions tab, not from a new sidebar entry.
 *
 * The run id comes from `useParams` rather than from the `params` prop: on Next
 * 14 `params` is a plain object, so `use(params)` throws at runtime — and because
 * the prop's type is whatever the page declares, `tsc` cannot catch that mistake.
 * `useParams` is correct here regardless of whether params later become a promise.
 */
import { Suspense } from "react";
import { useParams } from "next/navigation";

import { SuiteExecutionCommandCenter } from "@/components/execution/SuiteExecutionCommandCenter";

export default function SuiteExecutionLivePage() {
  const params = useParams<{ runId: string }>();
  const raw = Array.isArray(params?.runId) ? params.runId[0] : params?.runId;
  const runId = Number(raw);

  if (!raw || !Number.isInteger(runId) || runId <= 0) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-700">
        &quot;{raw ?? "(missing)"}&quot; is not a valid execution run id.
      </div>
    );
  }

  return (
    // The command center reads its filters from the query string, and
    // `useSearchParams` requires a Suspense boundary during prerender.
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center text-xs text-slate-500">
          Loading execution run…
        </div>
      }
    >
      <div className="h-[calc(100vh-8rem)]">
        <SuiteExecutionCommandCenter runId={runId} />
      </div>
    </Suspense>
  );
}
