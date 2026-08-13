"use client";

import { CheckCircle2, CircleSlash, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TasRefinedTestCase } from "@/lib/api";
import { EmptyState, GroundingBadge, SideDrawer, tasButtonTone } from "./shared";

/** Per-step evidence for one test case's grounding result.
 *
 *  The unresolved list is the point of this drawer. A badge saying "partly
 *  grounded" is only useful if the next click says *which* step failed and
 *  why — "no discovered element matches 'Login button'" is fixable, a colour
 *  is not.
 */
export function GroundingDrawer({
  testCase,
  onClose,
  onReground,
  regrounding = false,
}: {
  testCase: TasRefinedTestCase;
  onClose: () => void;
  onReground?: () => void;
  regrounding?: boolean;
}) {
  const summary = testCase.grounding_summary ?? {};
  const matched = summary.matched ?? [];
  const unresolved = summary.unresolved ?? [];
  const neverRan = testCase.grounding_status === "not_checked";

  return (
    <SideDrawer
      title={`Grounding — ${testCase.tc_display_id}`}
      subtitle={testCase.title}
      onClose={onClose}
      footer={
        <>
          {onReground && (
            <Button
              size="sm"
              variant="outline"
              className={tasButtonTone.live}
              onClick={onReground}
              disabled={regrounding}
            >
              {regrounding ? "Checking..." : "Check again"}
            </Button>
          )}
          <Button size="sm" variant="outline" className={tasButtonTone.neutral} onClick={onClose}>
            Close
          </Button>
        </>
      }
    >
      {neverRan ? (
        <EmptyState
          title="Grounding has not run for this test case"
          description="An automation engineer runs Discover Application and then Check Grounding from the Automation Script Lab. Until they do, this test case's script will use locators the model guessed rather than elements captured from the running application."
        />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <GroundingBadge status={testCase.grounding_status} />
            <span className="text-xs text-gray-600">
              {summary.matched_steps ?? 0} of {summary.groundable_steps ?? 0} step(s) resolved to a
              real element
            </span>
            {(summary.skipped_steps ?? 0) > 0 && (
              <span className="text-[11px] text-gray-500">
                · {summary.skipped_steps} step(s) need no element
              </span>
            )}
          </div>

          {summary.note && (
            <p className="rounded-lg border border-gray-200 bg-gray-50/70 px-3 py-2 text-xs text-gray-700">
              {summary.note}
            </p>
          )}

          {unresolved.length > 0 && (
            <section>
              <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-gray-900">
                <XCircle className="h-3.5 w-3.5 text-red-600" />
                Steps with no matching element ({unresolved.length})
              </h4>
              <ul className="space-y-2">
                {unresolved.map((gap, index) => (
                  <li
                    key={`${gap.step_number}-${index}`}
                    className="rounded-lg border border-red-200 bg-red-50/50 px-3 py-2"
                  >
                    <p className="text-xs font-medium text-gray-900">
                      Step {gap.step_number}
                      {gap.action ? ` — ${gap.action}` : ""}
                    </p>
                    {gap.target && (
                      <p className="mt-0.5 text-[11px] text-gray-700">
                        Target: <span className="font-medium">{gap.target}</span>
                      </p>
                    )}
                    <p className="mt-1 text-[11px] text-red-800">{gap.reason}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {matched.length > 0 && (
            <section>
              <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-gray-900">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                Steps bound to a discovered element ({matched.length})
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px]">
                  <thead className="border-b border-gray-200 text-gray-500">
                    <tr>
                      <th className="py-1.5 pr-3 font-medium">Step</th>
                      <th className="py-1.5 pr-3 font-medium">Test case says</th>
                      <th className="py-1.5 pr-3 font-medium">Real element</th>
                      <th className="py-1.5 pr-3 text-right font-medium">Conf.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {matched.map((match, index) => (
                      <tr key={`${match.step_number}-${index}`} className="align-top">
                        <td className="py-1.5 pr-3 tabular-nums text-gray-700">
                          {match.step_number}
                        </td>
                        <td className="py-1.5 pr-3 text-gray-700">{match.target ?? "—"}</td>
                        <td className="py-1.5 pr-3">
                          <p className="font-medium text-gray-900">{match.element_name}</p>
                          <code className="break-all font-mono text-[10px] text-gray-600">
                            {match.locator}
                          </code>
                        </td>
                        <td className="py-1.5 pr-3 text-right tabular-nums text-gray-600">
                          {match.confidence ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {matched.length === 0 && unresolved.length === 0 && (
            <div className="flex gap-2 rounded-lg border border-gray-200 bg-gray-50/70 px-3 py-2">
              <CircleSlash className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
              <p className="text-xs text-gray-600">
                No step in this test case names a UI control, so there was nothing to match against
                the discovered application.
              </p>
            </div>
          )}
        </div>
      )}
    </SideDrawer>
  );
}
