// UI-020/021/023 Automation Asset Workspace — the shell.
//
// One workspace, three tabs, over one Automation Suite member. The tabs are
// three views of ONE object at three stages of maturity, not three
// destinations: everything above the tab rail (identity, inherited context,
// autonomy badge, readiness strip) is shared and never re-rendered per tab.
//
// Section 21 rules this file is responsible for:
//   2. readiness in plain English, at the top, always
//   4. no field re-entered if inheritance already resolved it
//   5. no nested tab bars
//   7. every disabled control states why

"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, ChevronRight, Loader2, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { automationAssetApi, type AutomationAsset, type InheritedField } from "@/lib/api";

import { IrEditorTab } from "./IrEditorTab";
import { ScriptEditorTab } from "./ScriptEditorTab";
import { ValidationReviewTab } from "./ValidationReviewTab";
import { messageFromError, SuiteStatusBadge } from "./suite-shared";

export type AssetTabKey = "ir" | "script" | "validation";

const TAB_LABELS: Record<AssetTabKey, string> = {
  ir: "IR Editor",
  script: "Script Editor",
  validation: "Validation & Review",
};

/** Read-only inherited value with its source named. Never an input. */
function InheritedChip({ label, field }: { label: string; field: InheritedField }) {
  return (
    <div className="flex flex-col" title={field.available ? field.source ?? undefined : field.reason ?? undefined}>
      <span className="text-[9px] font-semibold uppercase tracking-wide text-gray-400">{label}</span>
      {field.available ? (
        <span className="text-[11px] font-medium text-gray-700">{field.value}</span>
      ) : (
        // Section 21 rule 8: absent data is an explained dash, never a zero.
        <span className="text-[11px] font-medium text-gray-400">—</span>
      )}
    </div>
  );
}

/** The one thing that tells the user what the machine has decided. Always visible. */
function AutonomyBadge({ asset }: { asset: AutomationAsset }) {
  const { autonomy_state, approval_state, score, threshold, enabled } = asset.autonomy;

  if (approval_state === "FINAL_APPROVED") {
    return <Badge variant="success">Final Approved</Badge>;
  }
  if (approval_state === "REJECTED") {
    return <Badge variant="destructive">Rejected</Badge>;
  }
  const scoreLabel = score === null ? "—" : `${score}/100`;
  if (autonomy_state === "AI_APPROVED") {
    return <Badge variant="success">{`AI Approved · ${scoreLabel}`}</Badge>;
  }
  if (autonomy_state === "AI_HELD") {
    return <Badge variant="warning">{`AI Held · ${scoreLabel}`}</Badge>;
  }
  return (
    <Badge
      variant="secondary"
      title={
        enabled
          ? "Not yet evaluated."
          : `Automatic approval is disabled for this project (threshold ${threshold}).`
      }
    >
      {`Not evaluated · ${scoreLabel}`}
    </Badge>
  );
}

const STRIP_TONE: Record<string, string> = {
  published: "border-purple-200 bg-purple-50 text-purple-800",
  no_ir: "border-gray-200 bg-gray-50 text-gray-700",
  ir_invalid: "border-red-200 bg-red-50 text-red-800",
  ir_incomplete: "border-amber-200 bg-amber-50 text-amber-900",
  ir_ready: "border-emerald-200 bg-emerald-50 text-emerald-800",
  ai_approved: "border-emerald-200 bg-emerald-50 text-emerald-800",
  ai_held: "border-amber-200 bg-amber-50 text-amber-900",
  final_approved: "border-emerald-200 bg-emerald-50 text-emerald-800",
  rejected: "border-red-200 bg-red-50 text-red-800",
};

/**
 * Section 10. Plain English, one primary action, never a bare spinner.
 * This is the direct answer to the "too many steps" feedback: the user reads
 * one sentence and clicks at most one button.
 */
function ReadinessStrip({
  asset,
  busyLabel,
  onPrimary,
}: {
  asset: AutomationAsset;
  busyLabel: string | null;
  onPrimary: (target: string) => void;
}) {
  const strip = asset.readiness_strip;
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border px-3 py-2",
        STRIP_TONE[strip.state] ?? "border-gray-200 bg-gray-50 text-gray-700",
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        {busyLabel ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
        ) : (
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
        )}
        {/* Work in progress names the stage being executed, never just a spinner. */}
        <span className="truncate text-[12px] font-medium">{busyLabel ?? strip.message}</span>
      </div>
      {strip.primary_action && strip.primary_action_target && !busyLabel ? (
        <Button
          size="sm"
          className="h-7 shrink-0 text-[11px]"
          onClick={() => onPrimary(strip.primary_action_target as string)}
        >
          {strip.primary_action}
          <ChevronRight className="ml-1 h-3 w-3" />
        </Button>
      ) : null}
    </div>
  );
}

export function AutomationAssetWorkspace({
  memberId,
  tab,
  onTabChange,
  onBackToSuite,
  onOpenRecorder,
}: {
  memberId: number;
  tab: AssetTabKey;
  onTabChange: (tab: AssetTabKey) => void;
  onBackToSuite: (suiteId: number) => void;
  onOpenRecorder: () => void;
}) {
  const [asset, setAsset] = useState<AutomationAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await automationAssetApi.get(memberId);
      setAsset(res.data);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoading(false);
    }
  }, [memberId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handlePrimary = useCallback(
    (target: string) => {
      if (target === "recorder") {
        onOpenRecorder();
        return;
      }
      if (target === "ir" || target === "script" || target === "validation") {
        onTabChange(target);
      }
    },
    [onOpenRecorder, onTabChange],
  );

  if (loading && !asset) {
    return (
      <div className="flex items-center gap-2 p-6 text-[12px] text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading automation asset…
      </div>
    );
  }

  if (error && !asset) {
    return (
      <div className="m-4 rounded-lg border border-red-200 bg-red-50 p-4 text-[12px] text-red-800">
        {error}
      </div>
    );
  }

  if (!asset) return null;

  const h = asset.header;

  return (
    <div className="space-y-3">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1 text-[11px] text-gray-500">
        <button className="hover:text-gray-800" onClick={() => onBackToSuite(h.suite_id)}>
          Automation
        </button>
        <ChevronRight className="h-3 w-3" />
        <button className="hover:text-gray-800" onClick={() => onBackToSuite(h.suite_id)}>
          {h.suite_name} v{h.suite_version}
        </button>
        <ChevronRight className="h-3 w-3" />
        <span className="font-medium text-gray-800">
          {h.test_case_display_id ?? `TC-${h.test_case_id}`}
        </span>
      </nav>

      {/* Header — identity, inherited context, autonomy badge. All read-only. */}
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-[15px] font-bold text-gray-900">
                {h.test_case_title ?? `Test case ${h.test_case_id}`}
              </h2>
              <SuiteStatusBadge status={h.suite_status} />
              <AutonomyBadge asset={asset} />
            </div>
            <p className="mt-0.5 text-[11px] text-gray-500">
              Suite member #{h.member_id} · {h.test_case_display_id ?? `TC-${h.test_case_id}`}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <InheritedChip label="Application" field={h.application} />
            <InheritedChip label="Framework" field={h.framework} />
            <InheritedChip label="Environment" field={h.environment} />
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className={cn("mr-1 h-3 w-3", loading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <ReadinessStrip asset={asset} busyLabel={busyLabel} onPrimary={handlePrimary} />

      {/* Tab rail. A tab not yet reachable is visible but disabled with its reason. */}
      <div className="flex items-center gap-1 border-b border-gray-200">
        {(Object.keys(TAB_LABELS) as AssetTabKey[]).map((key) => {
          const state = asset.tabs[key] ?? { enabled: true, reason: null };
          const active = tab === key;
          return (
            <button
              key={key}
              type="button"
              disabled={!state.enabled}
              title={state.enabled ? undefined : state.reason ?? undefined}
              onClick={() => state.enabled && onTabChange(key)}
              className={cn(
                "-mb-px border-b-2 px-3 py-1.5 text-[12px] font-semibold transition-colors",
                active
                  ? "border-app-brand-600 text-app-brand-700"
                  : "border-transparent text-gray-500 hover:text-gray-800",
                !state.enabled && "cursor-not-allowed text-gray-300 hover:text-gray-300",
              )}
            >
              {TAB_LABELS[key]}
            </button>
          );
        })}
      </div>

      {tab === "ir" ? (
        <IrEditorTab
          memberId={memberId}
          asset={asset}
          onReload={load}
          onBusyChange={setBusyLabel}
        />
      ) : null}

      {tab === "script" ? (
        <ScriptEditorTab
          memberId={memberId}
          asset={asset}
          onReload={load}
          onBusyChange={setBusyLabel}
          onEditBehaviour={() => onTabChange("ir")}
        />
      ) : null}

      {tab === "validation" ? (
        <ValidationReviewTab
          memberId={memberId}
          asset={asset}
          onReload={load}
          onBusyChange={setBusyLabel}
        />
      ) : null}
    </div>
  );
}
