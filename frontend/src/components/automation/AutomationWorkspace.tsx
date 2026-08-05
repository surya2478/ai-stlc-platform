"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ExternalLink,
  Code2,
  ListChecks,
  Database,
  Crosshair,
  CheckSquare,
  Activity,
  GitBranch,
  History,
  Sparkles,
  ShieldCheck,
  XCircle,
  PlayCircle,
  FileText,
  Loader2,
  Bot,
  Edit3,
  Network,
  Rocket,
  AlertTriangle,
  Check,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { LifecycleStepper, deriveLifecycleStage } from "./LifecycleStepper";
import { PipelineStageRail } from "./PipelineStageRail";
import {
  traceabilityApi,
  getScriptQualitySignals,
  getGenerationAttempts,
  type AutomationScript,
  type AutomationTestMapping,
  type LifecycleApprovalAction,
} from "@/lib/api";
import type { InventoryItem } from "./AutomationInventoryPanel";

type Tab =
  | "script"
  | "steps"
  | "test_data"
  | "locators"
  | "assertions"
  | "api_db"
  | "hooks"
  | "dependencies"
  | "history";

const TABS: { key: Tab; label: string; icon: typeof Code2 }[] = [
  { key: "script", label: "Script", icon: Code2 },
  { key: "steps", label: "Test Steps", icon: ListChecks },
  { key: "test_data", label: "Test Data", icon: Database },
  { key: "locators", label: "Locators", icon: Crosshair },
  { key: "assertions", label: "Assertions", icon: CheckSquare },
  { key: "api_db", label: "API / DB", icon: Activity },
  { key: "hooks", label: "Hooks", icon: GitBranch },
  { key: "dependencies", label: "Dependencies", icon: GitBranch },
  { key: "history", label: "History", icon: History },
];

/**
 * Statuses whose code body may be edited in place.
 *
 * The first three are the pre-Phase-2 authoring statuses. The rest are what the
 * Script Compiler actually produces today — without them the Edit button was
 * disabled for every compiler-generated script in the platform, since nothing
 * lands in `ai_draft`/`draft` any more. The backend never enforced this: PATCH
 * /automation/{id} checks the GENERATE_AUTOMATION permission and nothing else,
 * so this list is a UI guard, not the authority.
 *
 * Keep in sync with backend/app/models/automation_script.py's status docs.
 */
const EDITABLE_SCRIPT_STATUSES = new Set([
  "ai_draft",
  "draft",
  "rejected",
  "generated",
  "static_passed",
  "dry_run_passed",
]);

/** Why this script cannot be edited, naming the status that actually blocks it. */
function editLockReason(status: string): string {
  if (status === "approved") {
    return "Approved scripts are locked. Reject it to return it to draft before editing.";
  }
  if (status === "in_review" || status === "pending_approval") {
    return "This script is under review. Use Request Changes to return it to draft before editing.";
  }
  if (!status) {
    return "This script has no status, so it cannot be edited.";
  }
  return `Scripts in status "${status.replaceAll("_", " ")}" cannot be edited.`;
}

type TransitionAction = "submit_for_review" | "request_changes" | "restore_draft";

type Props = {
  item: InventoryItem | null;
  script: AutomationScript | null;
  mapping: AutomationTestMapping | null;
  busyApprove: boolean;
  busyTransition: boolean;
  busySave: boolean;
  busySandbox?: boolean;
  busyLifecycle?: boolean;
  onApprove: (action: "approve" | "reject") => Promise<void>;
  onLifecycleApprove: (action: LifecycleApprovalAction) => Promise<void>;
  onTransition: (action: TransitionAction) => Promise<void>;
  onSaveDraft: (code: string) => Promise<void>;
  onConfigureExternal: () => void;
  onRunSandbox: () => void;
  onOpenAssistant: () => void;
  onGenerate: () => void;
  /** Opens the traceability chain for the current script (omit to hide). */
  onTrace?: () => void;
};

export function AutomationWorkspace({
  item,
  script,
  mapping,
  busyApprove,
  busyTransition,
  busySave,
  busySandbox,
  busyLifecycle,
  onApprove,
  onLifecycleApprove,
  onTransition,
  onSaveDraft,
  onConfigureExternal,
  onRunSandbox,
  onOpenAssistant,
  onGenerate,
  onTrace,
}: Props) {
  const [tab, setTab] = useState<Tab>("script");
  const [editing, setEditing] = useState(false);
  const [draftCode, setDraftCode] = useState("");

  // Reset edit state when the active script changes.
  useEffect(() => {
    setEditing(false);
    setDraftCode(script?.code ?? "");
  }, [script?.id]);

  if (!item) {
    return (
      <Card className="border-gray-200">
        <CardContent className="flex h-full min-h-[360px] flex-col items-center justify-center gap-2 p-6 text-center">
          <Code2 className="h-8 w-8 text-gray-300" />
          <p className="text-sm font-semibold text-gray-700">No test case selected</p>
          <p className="max-w-xs text-xs text-gray-500">
            Pick a test case from the inventory on the left to load its automation workspace,
            review its script, and apply AI recommendations.
          </p>
        </CardContent>
      </Card>
    );
  }

  const isExternal = item.automationKind === "external";
  const externalVerified =
    isExternal && (item.automationReady || item.externalStatus === "verified");
  const { stage, variant } = deriveLifecycleStage(
    script?.status ?? null,
    isExternal,
    externalVerified,
  );

  return (
    <Card className="border-gray-200">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] text-gray-500">
              <span className="font-mono text-[#B71920]">{item.testCaseKey}</span>
              <span>·</span>
              <span>{isExternal ? item.externalTool ?? "External" : (item.framework ?? "—")}</span>
              {item.module && <><span>·</span><span>{item.module}</span></>}
            </div>
            <h2 className="mt-0.5 text-base font-bold text-gray-900 truncate" title={item.title}>
              {item.title}
            </h2>
            <p className="mt-0.5 text-[11px] text-gray-400">
              {script?.script_id ? `Script ${script.script_id}` : "No script yet"}
              {script?.updated_at && (
                <> · last modified {new Date(script.updated_at).toLocaleString()}</>
              )}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            {onTrace && script && (
              <Button
                variant="outline"
                size="sm"
                onClick={onTrace}
                className="gap-1.5"
                title="Show the Requirement → Test Case → Script → Run chain"
              >
                <Network className="h-3.5 w-3.5" />
                Trace
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={onOpenAssistant}
              className="gap-1.5 border-violet-200 text-violet-700 hover:bg-violet-50"
            >
              <Bot className="h-3.5 w-3.5" />
              AI Assistant
            </Button>
          </div>
        </div>

        <div className="rounded-lg border border-gray-100 bg-gray-50/50 px-3 py-2">
          {!isExternal && script ? (
            <PipelineStageRail scriptId={script.id} />
          ) : (
            <LifecycleStepper current={stage} variant={variant} />
          )}
        </div>

        <QualityBanner script={script} onGenerate={onGenerate} />
        <GenerationHistory script={script} />

        <ActionBar
          isExternal={isExternal}
          isGrounded={variant === "grounded"}
          stage={stage}
          gateFailed={script?.status === "generated" && script?.static_gate_result?.passed === false}
          scriptStatus={script?.status ?? null}
          busyApprove={busyApprove}
          busyTransition={busyTransition}
          busySandbox={busySandbox ?? false}
          busyLifecycle={busyLifecycle ?? false}
          hasScript={Boolean(script)}
          onApprove={onApprove}
          onLifecycleApprove={onLifecycleApprove}
          onTransition={onTransition}
          onConfigureExternal={onConfigureExternal}
          onRunSandbox={onRunSandbox}
        />

        {editing && script && draftCode !== script.code && (
          <p className="text-[11px] text-amber-700">
            You have unsaved changes. Use Save in the Script tab to keep them.
          </p>
        )}

        <div className="border-b border-gray-100">
          <div className="flex gap-0.5 overflow-x-auto">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  className={cn(
                    "flex shrink-0 items-center gap-1 rounded-t-md px-2.5 py-1.5 text-[11px] font-semibold transition",
                    active
                      ? "border-b-2 border-violet-600 text-violet-700"
                      : "text-gray-500 hover:text-gray-800",
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="min-h-[260px]">
          {tab === "script" && (
            <ScriptTab
              script={script}
              isExternal={isExternal}
              mapping={mapping}
              editing={editing}
              draftCode={draftCode}
              busySave={busySave}
              onStartEdit={() => {
                setDraftCode(script?.code ?? "");
                setEditing(true);
              }}
              onCancelEdit={() => {
                setEditing(false);
                setDraftCode(script?.code ?? "");
              }}
              onChange={setDraftCode}
              onSave={async () => {
                await onSaveDraft(draftCode);
                setEditing(false);
              }}
              onGenerate={onGenerate}
            />
          )}
          {tab === "steps" && <PlaceholderTab title="Test Steps" description="Inline view of the test case steps and how each maps to a script line. Available in Phase 2C." />}
          {tab === "test_data" && <PlaceholderTab title="Test Data" description="Data sets bound to this test, masking status, and reservation state. Available in Phase 2C." />}
          {tab === "locators" && <PlaceholderTab title="Locators" description="Per-locator stability scores and AI-suggested replacements. Open the AI Assistant panel for a preview." />}
          {tab === "assertions" && <PlaceholderTab title="Assertions" description="Existing assertions and gaps the AI has detected. Open the AI Assistant panel for a preview." />}
          {tab === "api_db" && <PlaceholderTab title="API / DB checks" description="Backend validations that pair with the UI steps. Open the AI Assistant panel for a preview." />}
          {tab === "hooks" && <PlaceholderTab title="Hooks" description="beforeAll / afterEach / fixtures wiring. Available in Phase 2C." />}
          {tab === "dependencies" && <PlaceholderTab title="Dependencies" description="Shared utilities, page objects, and external services this script depends on. Available in Phase 2C." />}
          {tab === "history" && <HistoryTab script={script} />}
        </div>
      </CardContent>
    </Card>
  );
}

/** Surfaces the same grounding/dry-run signals execution_blocked_reason()
 * gates on server-side — without this, "Approved" was the only status
 * visible here even when the script's own metadata already recorded that
 * it had ungrounded locators or a failed dry run. */
function QualityBanner({ script, onGenerate }: { script: AutomationScript | null; onGenerate: () => void }) {
  if (!script) return null;
  const quality = getScriptQualitySignals(script);

  if (quality.needsRegeneration) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-red-800">This script needs regeneration</p>
          <p className="mt-0.5 text-[11px] text-red-700">
            It predates a fix to how automation locators are grounded, and is known to contain
            locators that won&apos;t resolve on the real page. Execution is blocked until it&apos;s
            regenerated.
          </p>
        </div>
        <Button size="sm" onClick={onGenerate} className="shrink-0 gap-1.5 bg-red-600 text-white hover:bg-red-700">
          <Sparkles className="h-3.5 w-3.5" />
          Regenerate
        </Button>
      </div>
    );
  }

  // Phase 2.5's Static Quality Gate (see static_quality_gate.py) runs
  // synchronously right after generation. A failing gate leaves status
  // "generated" forever — the script is silently excluded from the
  // automatic dry-run chain (agent_tasks._build_dry_run_input only picks up
  // "static_passed") and never reaches the repair loop either, since that
  // only triggers after a dry run. Regeneration is the only way forward.
  if (script.status === "generated" && script.static_gate_result?.passed === false) {
    const violations = script.static_gate_result.violations ?? [];
    return (
      <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-red-800">Static quality gate failed</p>
          {violations.length > 0 && (
            <ul className="mt-1 space-y-0.5 text-[11px] text-red-700">
              {violations.map((v, i) => (
                <li key={i}>• {v.message}</li>
              ))}
            </ul>
          )}
          <p className="mt-1 text-[11px] text-red-700">
            This script won&apos;t reach dry run or review on its own — regenerate it to clear
            these violations.
          </p>
        </div>
        <Button size="sm" onClick={onGenerate} className="shrink-0 gap-1.5 bg-red-600 text-white hover:bg-red-700">
          <Sparkles className="h-3.5 w-3.5" />
          Regenerate
        </Button>
      </div>
    );
  }

  if (quality.ungroundedElements.length > 0) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-amber-800">
            {quality.ungroundedElements.length} element{quality.ungroundedElements.length > 1 ? "s" : ""} not grounded to a real page
          </p>
          <p className="mt-0.5 truncate text-[11px] text-amber-700" title={quality.ungroundedElements.join(", ")}>
            {quality.ungroundedElements.join(", ")} — this script will likely fail on execution.
          </p>
        </div>
        <Button size="sm" onClick={onGenerate} variant="outline" className="shrink-0 gap-1.5 border-amber-300 text-amber-800 hover:bg-amber-100">
          <Sparkles className="h-3.5 w-3.5" />
          Regenerate
        </Button>
      </div>
    );
  }

  if (quality.lastDryRunPassed === false) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-amber-800">Last dry run failed</p>
          <p className="mt-0.5 text-[11px] text-amber-700">
            This script&apos;s most recent dry run did not pass. Review the failure before running it
            again — retrying the same script won&apos;t change the outcome.
          </p>
        </div>
      </div>
    );
  }

  return null;
}

const GENERATION_OUTCOME_LABELS: Record<string, string> = {
  compiled: "Compiled",
  validation_failed: "Validation failed",
  parse_failed: "Response wasn't valid JSON",
  llm_error: "LLM call failed",
};

/** Every attempt the generation feedback loop made — validation/parse
 * failures it corrected, or grounding it kept narrowing — on the way to
 * this script's result. Was previously entirely invisible: a script that
 * needed 3 retries looked identical to one that succeeded on the first
 * try, so generation felt like a slot machine rather than a loop that
 * converges. Only rendered when there's more than one attempt — a clean
 * first-try success has nothing to show. */
function GenerationHistory({ script }: { script: AutomationScript | null }) {
  if (!script) return null;
  const attempts = getGenerationAttempts(script);
  if (attempts.length <= 1) return null;

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50/60 px-3 py-2">
      <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-gray-700">
        <History className="h-3 w-3" />
        Generation took {attempts.length} attempts
      </p>
      <ul className="space-y-1">
        {attempts.map((a) => (
          <li key={a.attempt} className="flex items-start gap-1.5 text-[11px] text-gray-600">
            {a.outcome === "compiled" ? (
              <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" />
            ) : (
              <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-gray-400" />
            )}
            <span>
              <span className="font-mono">#{a.attempt}</span>{" "}
              {GENERATION_OUTCOME_LABELS[a.outcome] ?? a.outcome}
              {a.outcome === "compiled" && typeof a.ungrounded_count === "number"
                ? a.ungrounded_count > 0
                  ? ` — ${a.ungrounded_count} element(s) still ungrounded`
                  : " — fully grounded"
                : ""}
              {a.detail ? ` — ${a.detail.split("\n")[0]}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ActionBar({
  isExternal,
  isGrounded,
  stage,
  gateFailed,
  scriptStatus,
  busyApprove,
  busyTransition,
  busySandbox,
  busyLifecycle,
  hasScript,
  onApprove,
  onLifecycleApprove,
  onTransition,
  onConfigureExternal,
  onRunSandbox,
}: {
  isExternal: boolean;
  isGrounded: boolean;
  stage: string;
  gateFailed: boolean;
  scriptStatus: string | null;
  busyApprove: boolean;
  busyTransition: boolean;
  busySandbox: boolean;
  busyLifecycle: boolean;
  hasScript: boolean;
  onApprove: (action: "approve" | "reject") => Promise<void>;
  onLifecycleApprove: (action: LifecycleApprovalAction) => Promise<void>;
  onTransition: (action: TransitionAction) => Promise<void>;
  onConfigureExternal: () => void;
  onRunSandbox: () => void;
}) {
  if (isExternal) {
    return (
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={onConfigureExternal} className="gap-1.5">
          <ExternalLink className="h-3.5 w-3.5" />
          Configure connection
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onConfigureExternal}
          className="gap-1.5"
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          Verify
        </Button>
      </div>
    );
  }

  if (isGrounded && hasScript) {
    return (
      <GroundedActionBar stage={stage} gateFailed={gateFailed} busy={busyLifecycle} onApprove={onLifecycleApprove} />
    );
  }

  // Mirror the backend transition map (automation_service.py _TRANSITIONS):
  // submit_for_review: ai_draft|draft, request_changes: in_review|pending_approval,
  // restore_draft: rejected|deprecated. Approve/reject act on in_review scripts.
  const status = (scriptStatus ?? "").toLowerCase();
  const canSubmit = hasScript && (status === "ai_draft" || status === "draft");
  const canRequestChanges = hasScript && (status === "in_review" || status === "pending_approval");
  const canApprove = hasScript && stage === "in_review";
  const canRestore = hasScript && (status === "rejected" || status === "deprecated");
  // The local runner only accepts approved/executed scripts (see
  // POST /automation/scripts/{id}/execute).
  const canRunSandbox = hasScript && (status === "approved" || status === "executed");

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={!canSubmit || busyTransition}
        onClick={() => onTransition("submit_for_review")}
        className="gap-1.5"
      >
        {busyTransition ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        Submit for review
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={!canRequestChanges || busyTransition}
        onClick={() => onTransition("request_changes")}
        className="gap-1.5"
      >
        <FileText className="h-3.5 w-3.5" />
        Request changes
      </Button>
      {canRestore && (
        <Button
          variant="outline"
          size="sm"
          disabled={busyTransition}
          onClick={() => onTransition("restore_draft")}
          className="gap-1.5"
          title="Bring this script back to Draft for another iteration"
        >
          <FileText className="h-3.5 w-3.5" />
          Restore draft
        </Button>
      )}
      <Button
        size="sm"
        disabled={!canApprove || busyApprove}
        onClick={() => onApprove("approve")}
        className="gap-1.5 bg-emerald-600 text-white hover:bg-emerald-700"
      >
        {busyApprove ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
        Approve
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={!canApprove || busyApprove}
        onClick={() => onApprove("reject")}
        className="gap-1.5 border-red-200 text-red-700 hover:bg-red-50"
      >
        <XCircle className="h-3.5 w-3.5" />
        Reject
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={!canRunSandbox || busySandbox}
        onClick={onRunSandbox}
        className="gap-1.5"
        title={canRunSandbox ? "Execute on the backend host via the local runner" : "Only approved scripts can run — complete review and approval first"}
      >
        {busySandbox ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />}
        Run in sandbox
      </Button>
    </div>
  );
}

// Phase 4.6: staged post-generation approval chain for the grounded
// generation pipeline (dry_run_passed -> reviewer_approved -> lead_approved
// -> [environment_approve, required for PROD_SANITY] -> ci_ready). "Static
// Gate Passed" and "Generated" have no human action here — the static gate
// and dry run are automatic pipeline steps; a human only steps in once a
// script has actually proven it runs.
function GroundedActionBar({
  stage,
  gateFailed,
  busy,
  onApprove,
}: {
  stage: string;
  gateFailed: boolean;
  busy: boolean;
  onApprove: (action: LifecycleApprovalAction) => Promise<void>;
}) {
  if (stage === "generated" && gateFailed) {
    return (
      <p className="text-[11px] text-gray-500">
        The static quality gate failed — see the notice above to view the violations and
        regenerate.
      </p>
    );
  }

  if (stage === "generated" || stage === "static_passed") {
    return (
      <p className="text-[11px] text-gray-500">
        Waiting on the automatic static quality gate and dry run to finish before this script
        can be reviewed. No action needed here yet.
      </p>
    );
  }

  if (stage === "dry_run_passed") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={busy}
          onClick={() => onApprove("reviewer_approve")}
          className="gap-1.5 bg-emerald-600 text-white hover:bg-emerald-700"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          Reviewer approve
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => onApprove("reviewer_reject")}
          className="gap-1.5 border-red-200 text-red-700 hover:bg-red-50"
        >
          <XCircle className="h-3.5 w-3.5" />
          Reject
        </Button>
      </div>
    );
  }

  if (stage === "reviewer_approved") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={busy}
          onClick={() => onApprove("lead_approve")}
          className="gap-1.5 bg-emerald-600 text-white hover:bg-emerald-700"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          Lead approve
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => onApprove("lead_reject")}
          className="gap-1.5 border-red-200 text-red-700 hover:bg-red-50"
        >
          <XCircle className="h-3.5 w-3.5" />
          Reject
        </Button>
      </div>
    );
  }

  if (stage === "lead_approved") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => onApprove("environment_approve")}
          className="gap-1.5"
          title="Required before Mark CI ready when the script targets PROD_SANITY"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          Environment approve
        </Button>
        <Button
          size="sm"
          disabled={busy}
          onClick={() => onApprove("mark_ci_ready")}
          className="gap-1.5 bg-emerald-600 text-white hover:bg-emerald-700"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Rocket className="h-3.5 w-3.5" />}
          Mark CI ready
        </Button>
      </div>
    );
  }

  if (stage === "ci_ready") {
    return (
      <p className="text-[11px] font-semibold text-emerald-700">
        This script is CI-ready and part of the regression suite.
      </p>
    );
  }

  return null;
}

function ScriptTab({
  script,
  isExternal,
  mapping,
  editing,
  draftCode,
  busySave,
  onStartEdit,
  onCancelEdit,
  onChange,
  onSave,
  onGenerate,
}: {
  script: AutomationScript | null;
  isExternal: boolean;
  mapping: AutomationTestMapping | null;
  editing: boolean;
  draftCode: string;
  busySave: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onChange: (next: string) => void;
  onSave: () => Promise<void>;
  onGenerate: () => void;
}) {
  if (isExternal) {
    return (
      <div className="space-y-3">
        <p className="text-[11px] text-gray-500">
          External automation. Script lives in the connected tool; QAI orchestrates the run
          and pulls back evidence.
        </p>
        {mapping ? (
          <div className="rounded-lg border border-gray-200 p-3 space-y-1.5 text-xs">
            <Row label="Tool" value={mapping.external_tool_name} />
            <Row label="Project" value={mapping.external_project_id ?? "—"} />
            <Row label="Suite" value={mapping.external_suite_id ?? "—"} />
            <Row label="External TC" value={mapping.external_test_case_id} />
            <Row label="Script ID" value={mapping.external_script_id ?? "—"} />
            <Row label="Status" value={mapping.automation_status} />
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-gray-200 p-4 text-center text-xs text-gray-400">
            No external mapping yet. Configure the connection to link this test case.
          </div>
        )}
      </div>
    );
  }

  if (!script || !script.code) {
    return (
      <div className="rounded-lg border border-dashed border-gray-200 p-6 text-center">
        <p className="text-xs text-gray-500">No script generated for this test case yet.</p>
        <p className="mt-1 text-[11px] text-gray-400">
          Generate a draft Playwright or Pytest script with AI, preselected for this test case.
        </p>
        <Button
          type="button"
          size="sm"
          onClick={onGenerate}
          className="mt-3 gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
        >
          <Sparkles className="h-3.5 w-3.5" />
          Generate with AI
        </Button>
      </div>
    );
  }

  const lineCount = (editing ? draftCode : script.code).split("\n").length;
  const dirty = editing && draftCode !== script.code;
  const stage = (script.status ?? "").toLowerCase();
  const editable = EDITABLE_SCRIPT_STATUSES.has(stage);
  const lockReason = editable ? "" : editLockReason(stage);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px] text-gray-500">
        <span>
          {script.framework.toUpperCase()} · {lineCount} lines
          {editing && dirty && (
            <span className="ml-2 rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
              unsaved
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          {script.execution_command && (
            <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-700">
              {script.execution_command}
            </code>
          )}
          {!editing ? (
            <Button
              size="sm"
              variant="outline"
              disabled={!editable}
              onClick={onStartEdit}
              className="gap-1.5"
              title={lockReason}
            >
              <Edit3 className="h-3.5 w-3.5" />
              Edit code
            </Button>
          ) : (
            <>
              <Button size="sm" variant="outline" onClick={onCancelEdit} disabled={busySave}>
                Cancel
              </Button>
              <Button size="sm" onClick={onSave} disabled={!dirty || busySave} className="gap-1.5">
                {busySave ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
                Save draft
              </Button>
            </>
          )}
        </div>
      </div>
      {editing ? (
        <textarea
          value={draftCode}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="block max-h-[480px] min-h-[280px] w-full overflow-auto rounded-lg border border-gray-300 bg-gray-950 p-3 font-mono text-[11px] leading-relaxed text-gray-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
        />
      ) : (
        <pre className="max-h-[360px] overflow-auto rounded-lg border border-gray-200 bg-gray-950 p-3 text-[11px] leading-relaxed text-gray-100">
          <code>{script.code}</code>
        </pre>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[11px] text-gray-500">{label}</span>
      <span className="font-mono text-[11px] text-gray-800 truncate">{value}</span>
    </div>
  );
}

/**
 * Review & lifecycle history for the selected script: approval decisions from
 * the governance ledger plus the state-machine transitions recorded in
 * `metadata_.transition_history`.
 */
function HistoryTab({ script }: { script: AutomationScript | null }) {
  const approvalsQuery = useQuery({
    queryKey: ["traceability", "approvals", "automation_script", script?.id],
    enabled: script !== null,
    queryFn: async () =>
      (
        await traceabilityApi.approvals(script!.project_id, {
          entity_type: "automation_script",
          entity_id: script!.id,
        })
      ).data,
  });

  if (!script) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-gray-200 p-6 text-xs text-gray-400">
        No script selected.
      </div>
    );
  }

  const transitions = Array.isArray((script.metadata_ as { transition_history?: unknown })?.transition_history)
    ? ((script.metadata_ as { transition_history: Array<{ action?: string; notes?: string; to?: string }> }).transition_history)
    : [];
  const approvals = approvalsQuery.data ?? [];

  const decisionBadge = (decision: string): "success" | "destructive" | "warning" | "secondary" => {
    if (decision === "approved") return "success";
    if (decision === "rejected") return "destructive";
    if (decision === "requested_changes") return "warning";
    return "secondary";
  };

  if (approvalsQuery.isLoading) {
    return (
      <div className="flex h-48 items-center justify-center text-xs text-gray-400">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading review history…
      </div>
    );
  }

  if (approvals.length === 0 && transitions.length === 0) {
    return (
      <div className="flex h-48 flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-gray-200 p-6 text-center">
        <History className="h-5 w-5 text-gray-300" />
        <p className="text-xs font-semibold text-gray-700">No review history yet</p>
        <p className="max-w-md text-[11px] text-gray-500">
          Approvals, rejections, and lifecycle transitions for this script will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {approvals.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
            Approval decisions
          </p>
          <ul className="space-y-1.5">
            {approvals.map((a) => (
              <li key={a.id} className="rounded-lg border border-gray-100 px-3 py-2 text-[11px]">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={decisionBadge(a.decision)} className="text-[9px] capitalize">
                    {a.decision.replace(/_/g, " ")}
                  </Badge>
                  {a.actor_role && <span className="text-gray-500">by {a.actor_role}</span>}
                  <span className="ml-auto text-gray-400">{new Date(a.created_at).toLocaleString()}</span>
                </div>
                {a.notes && <p className="mt-1 text-gray-600">{a.notes}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {transitions.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
            Lifecycle transitions
          </p>
          <ul className="space-y-1.5">
            {[...transitions].reverse().map((t, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-100 px-3 py-2 text-[11px]">
                <span className="font-semibold capitalize text-gray-700">
                  {(t.action ?? "").replace(/_/g, " ")}
                </span>
                {t.to && (
                  <>
                    <span className="text-gray-300">→</span>
                    <Badge variant="outline" className="text-[9px] capitalize">{t.to.replace(/_/g, " ")}</Badge>
                  </>
                )}
                {t.notes && <span className="text-gray-500">— {t.notes}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function PlaceholderTab({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-gray-200 p-6 text-center">
      <Badge variant="outline" className="text-[10px]">Phase 2C</Badge>
      <p className="text-xs font-semibold text-gray-700">{title}</p>
      <p className="max-w-md text-[11px] text-gray-500">{description}</p>
    </div>
  );
}
