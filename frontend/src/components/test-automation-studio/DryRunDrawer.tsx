"use client";

import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { TasScriptAsset } from "@/lib/api";
import {
  DryRunBadge,
  EmptyState,
  GenerationModeBadge,
  SideDrawer,
  tasButtonTone,
} from "./shared";

/** Everything known about whether one generated script actually works.
 *
 *  Three separate questions, deliberately shown together because they fail
 *  independently: was it compiled or hand-written by the model, did it pass
 *  the static gate, and did it run. A script can be beautifully compiled,
 *  clear the gate, and still fail on the first locator — which is exactly the
 *  case this drawer exists to make legible.
 */
export function DryRunDrawer({
  script,
  onClose,
  onRerun,
  rerunning = false,
}: {
  script: TasScriptAsset;
  onClose: () => void;
  onRerun?: () => void;
  rerunning?: boolean;
}) {
  const summary = script.dry_run_summary ?? {};
  const results = summary.results ?? [];
  const grounding = script.grounding ?? {};
  const gate = script.static_gate_result ?? {};
  const violations = gate.violations ?? [];
  const warnings = gate.warnings ?? [];
  const ungrounded = grounding.ungrounded_elements ?? [];

  return (
    <SideDrawer
      title={`Verification — ${script.test_case_display_id ?? script.script_key}`}
      subtitle={script.test_case_title ?? undefined}
      onClose={onClose}
      footer={
        <>
          {onRerun && script.dry_run_status !== "blocked" && (
            <Button
              size="sm"
              variant="outline"
              className={tasButtonTone.live}
              onClick={onRerun}
              disabled={rerunning}
            >
              {rerunning ? "Queuing..." : "Run again"}
            </Button>
          )}
          <Button size="sm" variant="outline" className={tasButtonTone.neutral} onClick={onClose}>
            Close
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <GenerationModeBadge mode={script.generation_mode} />
          <DryRunBadge status={script.dry_run_status} />
          {script.dry_run_at && (
            <span className="text-[11px] text-gray-500">
              last run {new Date(script.dry_run_at).toLocaleString()}
            </span>
          )}
        </div>

        {/* Grounding first: an ungrounded locator is the most common reason a
            dry run fails, so naming it above the failure saves a round trip. */}
        <section className="rounded-lg border border-gray-200 px-3 py-2">
          <h4 className="text-xs font-semibold text-gray-900">Locator grounding</h4>
          {script.generation_mode === "freeform" ? (
            <p className="mt-1 text-[11px] text-gray-600">
              This framework has no compiler, so the discovered elements were supplied to the model
              as a reference but could not be substituted into its output.{" "}
              {grounding.catalog_size
                ? `${grounding.catalog_size} discovered element(s) were available.`
                : "No discovery run was available for this batch."}
            </p>
          ) : (
            <p className="mt-1 text-[11px] text-gray-600">
              {grounding.grounded_elements ?? 0} element(s) were bound directly to discovered
              evidence out of a catalog of {grounding.catalog_size ?? 0}.
            </p>
          )}
          {ungrounded.length > 0 && (
            <div className="mt-1.5">
              <p className="text-[11px] font-medium text-amber-800">
                Not backed by evidence ({ungrounded.length}) — these may not match the real page:
              </p>
              <ul className="mt-1 flex flex-wrap gap-1">
                {ungrounded.map((ref) => (
                  <li key={ref}>
                    <Badge variant="warning">{ref}</Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {script.generation_mode === "compiled" && (
          <section className="rounded-lg border border-gray-200 px-3 py-2">
            <h4 className="flex items-center gap-1.5 text-xs font-semibold text-gray-900">
              {gate.passed ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              ) : (
                <XCircle className="h-3.5 w-3.5 text-red-600" />
              )}
              Static quality gate
            </h4>
            {violations.length === 0 && warnings.length === 0 && (
              <p className="mt-1 text-[11px] text-gray-600">No findings.</p>
            )}
            {violations.length > 0 && (
              <ul className="mt-1.5 space-y-1">
                {violations.map((violation, index) => (
                  <li
                    key={`${violation.code}-${index}`}
                    className="rounded border border-red-200 bg-red-50/50 px-2 py-1 text-[11px] text-red-800"
                  >
                    <span className="font-medium">{violation.code}</span> — {violation.message}
                  </li>
                ))}
              </ul>
            )}
            {warnings.length > 0 && (
              <ul className="mt-1.5 space-y-1">
                {warnings.slice(0, 8).map((warning, index) => (
                  <li
                    key={`${warning.code}-${index}`}
                    className="rounded border border-amber-200 bg-amber-50/50 px-2 py-1 text-[11px] text-amber-800"
                  >
                    <span className="font-medium">{warning.code}</span> — {warning.message}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {script.dry_run_status === "blocked" && (
          <div className="flex gap-2 rounded-lg border border-gray-200 bg-gray-50/70 px-3 py-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
            <p className="text-xs text-gray-700">{summary.reason}</p>
          </div>
        )}

        {script.dry_run_status === "not_run" && (
          <EmptyState
            title="This script has not been executed"
            description="Until it runs, whether it works is an assumption. Select it on the grid and choose Dry Run to find out."
          />
        )}

        {summary.error_message && (
          <div className="flex gap-2 rounded-lg border border-red-200 bg-red-50/70 px-3 py-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
            <p className="min-w-0 whitespace-pre-wrap break-words text-[11px] text-red-800">
              {summary.error_message}
            </p>
          </div>
        )}

        {results.length > 0 && (
          <section>
            <h4 className="mb-1.5 text-xs font-semibold text-gray-900">
              Test results ({results.length})
            </h4>
            <ul className="space-y-2">
              {results.map((result, index) => (
                <li
                  key={`${result.name}-${index}`}
                  className={
                    result.status === "pass"
                      ? "rounded-lg border border-emerald-200 bg-emerald-50/40 px-3 py-2"
                      : "rounded-lg border border-red-200 bg-red-50/40 px-3 py-2"
                  }
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="min-w-0 text-xs font-medium text-gray-900">{result.name}</p>
                    <div className="flex shrink-0 items-center gap-2">
                      {result.duration_ms != null && (
                        <span className="text-[10px] tabular-nums text-gray-500">
                          {result.duration_ms} ms
                        </span>
                      )}
                      <Badge variant={result.status === "pass" ? "success" : "destructive"}>
                        {result.status}
                      </Badge>
                    </div>
                  </div>
                  {result.error_message && (
                    <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-white/70 p-2 font-mono text-[10px] text-red-800">
                      {result.error_message}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {script.setup_notes.length > 0 && (
          <section>
            <h4 className="mb-1.5 text-xs font-semibold text-gray-900">Setup still required</h4>
            <ul className="space-y-1">
              {script.setup_notes.map((note, index) => (
                <li key={index} className="flex gap-2 text-[11px] text-gray-600">
                  <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
                  <span>{note}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </SideDrawer>
  );
}
