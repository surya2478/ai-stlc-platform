"use client";

import { Loader2, Radar } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ProjectApplication, TestCase, TestCaseAutomationClassification } from "@/lib/api";

/**
 * The step between Test Case Approval and the automation flow.
 *
 * An approved test case only becomes automatable once it is mapped to a
 * registered application: Live Discovery Session is scoped to exactly one
 * application, the Application Model it produces is per-application, and the
 * locator evidence AI Automation Studio generates against is keyed by
 * application. Without the mapping the test case is stranded — approved, marked
 * automation-eligible, and unable to enter any of it.
 *
 * The panel does two things and says why: set the mapping, then hand off to
 * discovery. It does not gate approval — a manual-only test case never needs an
 * application, so this is stated as the next step in one path, not a defect in
 * the test case.
 */
export function AutomationHandoffPanel({
  testCase,
  applications,
  busy,
  classification,
  onSaveApplication,
  onStartDiscovery,
}: {
  testCase: TestCase;
  applications: ProjectApplication[];
  busy: boolean;
  classification?: TestCaseAutomationClassification | null;
  onSaveApplication: (applicationId: number | null) => void;
  onStartDiscovery: (applicationId: number) => void;
}) {
  const mappedId = testCase.application_id ?? null;
  const mapped = applications.find((a) => a.id === mappedId) ?? null;
  const isApproved = testCase.status === "approved" || testCase.approval_status === "approved";
  const automationIntended =
    testCase.automation_eligible === "yes" || testCase.execution_mode !== "manual";

  /**
   * A test case stays `execution_mode: manual` until its classification is
   * approved — that approval is what writes `execution_mode`,
   * `automation_eligible` and `automation_status` (classification_service.py
   * ::_apply_approval_to_test_case). So a recommended-but-unapproved
   * classification reads as a flat contradiction here: the classification card
   * says RECOMMENDED / PLAYWRIGHT_MCP while this panel says "Manual test case"
   * and never says the decision is simply still pending. Name the pending
   * decision instead.
   */
  const awaitingClassificationApproval =
    !automationIntended &&
    classification != null &&
    classification.review_status !== "APPROVED" &&
    (classification.candidate_status === "RECOMMENDED" ||
      classification.candidate_status === "CONDITIONAL");

  return (
    <div className="space-y-4">
      <div>
        <p className="text-[10px] font-extrabold uppercase tracking-wide text-gray-400">
          Application under test
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            value={mappedId ?? ""}
            disabled={busy || applications.length === 0}
            onChange={(event) =>
              onSaveApplication(event.target.value ? Number(event.target.value) : null)
            }
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#B71920] disabled:bg-gray-50 disabled:text-gray-400"
          >
            <option value="">Not mapped</option>
            {applications.map((app) => (
              <option key={app.id} value={app.id ?? ""}>
                {app.name}
                {app.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />}
        </div>
        {applications.length === 0 && (
          <p className="mt-2 text-[11px] font-semibold text-amber-700">
            No active applications are registered for this project. Add one in the Application
            Registry before mapping test cases to it.
          </p>
        )}
      </div>

      {awaitingClassificationApproval ? (
        <div className="rounded-lg border border-app-brand-200 bg-app-brand-75 p-3">
          <p className="text-xs font-extrabold text-app-brand-900">Manual until the classification is approved</p>
          <p className="mt-1 text-[11px] font-semibold leading-5 text-app-brand-800">
            Automation classification recommends{" "}
            <span className="font-bold">{classification?.candidate_status.replace(/_/g, " ")}</span>
            {classification?.primary_adapter ? (
              <>
                {" "}
                via <span className="font-bold">{classification.primary_adapter}</span>
              </>
            ) : null}
            , but the review is still {classification?.review_status.replace(/_/g, " ").toLowerCase()}.
            Approving that classification is what marks this test case automation-eligible and opens
            discovery and script generation.
          </p>
        </div>
      ) : !automationIntended ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p className="text-xs font-extrabold text-gray-700">Manual test case</p>
          <p className="mt-1 text-[11px] font-semibold leading-5 text-gray-600">
            Discovery and script generation do not apply. Mapping an application is still useful for
            reporting and execution routing.
          </p>
        </div>
      ) : !mapped ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs font-extrabold text-amber-900">Map an application to continue</p>
          <p className="mt-1 text-[11px] font-semibold leading-5 text-amber-800">
            Live Discovery Session runs against one registered application and will reject this test
            case until it is mapped to one.
          </p>
        </div>
      ) : !isApproved ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p className="text-xs font-extrabold text-gray-700">Approve this test case first</p>
          <p className="mt-1 text-[11px] font-semibold leading-5 text-gray-600">
            Discovery only accepts approved test cases. Mapped to{" "}
            <span className="font-bold">{mapped.name}</span> and ready once approval lands.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-emerald-100 bg-emerald-50 p-3">
          <p className="text-xs font-extrabold text-emerald-800">Ready for Live Discovery Session</p>
          <p className="mt-1 text-[11px] font-semibold leading-5 text-emerald-700">
            Approved and mapped to <span className="font-bold">{mapped.name}</span>. Discovery
            captures the real screens and locators; publishing an Application Model from it is what
            grounds the generated script in AI Automation Studio.
          </p>
          <Button
            size="sm"
            className="mt-3"
            onClick={() => mapped.id != null && onStartDiscovery(mapped.id)}
            disabled={mapped.id == null}
          >
            <Radar className="h-3.5 w-3.5" /> Start Live Discovery Session
          </Button>
        </div>
      )}
    </div>
  );
}
