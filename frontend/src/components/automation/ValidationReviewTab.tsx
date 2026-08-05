// UI-023 Validation and Review — Tab C.
//
// The only tab where a human decision is recorded, and the only place the two
// axes are shown side by side:
//
//   Gating decision   — the MACHINE axis (autonomy_state). Computed, not clicked.
//   Approval workflow — the HUMAN axis (approval_state). Never written by the machine.
//
// They are deliberately not one stepper. AI_APPROVED has no node in the human
// workflow: putting it there would let the generating agent write the field a
// reviewer writes, which is the separation-of-duty violation the platform
// already refuses for human actors.

"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Ban,
  Check,
  CircleSlash,
  Loader2,
  Send,
  ShieldCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import {
  automationValidationApi,
  type AssetDecisionRow,
  type AutomationAsset,
  type ValidationCard,
  type ValidationPayload,
} from "@/lib/api";

import { messageFromError, Panel } from "./suite-shared";

const DETAIL_TABS = ["Static quality", "Execution", "Readiness", "Confidence"] as const;
type DetailTab = (typeof DETAIL_TABS)[number];

/** The human axis, exactly as drawn in the reference image. */
const WORKFLOW_STEPS = ["Draft", "Pending Review", "Changes Requested", "Approved", "Published"];

function SummaryCard({ card }: { card: ValidationCard }) {
  const tone =
    !card.available
      ? "border-gray-200 bg-gray-50 text-gray-400"
      : card.status === "pass"
        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
        : card.status === "fail"
          ? "border-red-200 bg-red-50 text-red-800"
          : "border-amber-200 bg-amber-50 text-amber-900";
  return (
    <div
      className={cn("rounded-lg border p-2.5", tone)}
      title={card.available ? undefined : card.reason ?? undefined}
    >
      <p className="text-[9px] font-semibold uppercase tracking-wide opacity-70">{card.label}</p>
      <p className="mt-0.5 text-[15px] font-bold">
        {/* Absent evidence is an explained dash, never a zero and never a pass. */}
        {card.available ? card.status : "—"}
      </p>
      <p className="text-[10px] opacity-80">{card.available ? card.detail : card.reason}</p>
    </div>
  );
}

export function ValidationReviewTab({
  memberId,
  asset,
  onReload,
  onBusyChange,
}: {
  memberId: number;
  asset: AutomationAsset;
  onReload: () => Promise<void> | void;
  onBusyChange: (label: string | null) => void;
}) {
  const { toast } = useToast();
  const [data, setData] = useState<ValidationPayload | null>(null);
  const [decisions, setDecisions] = useState<AssetDecisionRow[]>([]);
  const [detailTab, setDetailTab] = useState<DetailTab>("Static quality");
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [v, d] = await Promise.all([
        automationValidationApi.get(memberId),
        automationValidationApi.decisions(memberId),
      ]);
      setData(v.data);
      setDecisions(d.data);
    } catch (err) {
      toast({
        title: "Could not load validation",
        description: messageFromError(err),
        variant: "error",
      });
    } finally {
      setLoading(false);
    }
  }, [memberId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleAccept = useCallback(
    async (code: string) => {
      const reason = window.prompt(
        `Reason for accepting '${code}' as an exception (recorded against the script):`,
      );
      if (!reason || !reason.trim()) return;
      setActing(true);
      onBusyChange("Accepting exception…");
      try {
        await automationValidationApi.acceptException(memberId, code, reason);
        toast({ title: `Exception accepted for ${code}` });
        await load();
        await onReload();
      } catch (err) {
        toast({ title: "Could not accept", description: messageFromError(err), variant: "error" });
      } finally {
        setActing(false);
        onBusyChange(null);
      }
    },
    [load, memberId, onBusyChange, onReload, toast],
  );

  const handleDecision = useCallback(
    async (approve: boolean) => {
      let reason: string | null = null;
      if (!approve) {
        reason = window.prompt("Reason for rejection (required, recorded in the audit trail):");
        if (!reason || !reason.trim()) return;
      }
      setActing(true);
      onBusyChange(approve ? "Recording final approval…" : "Recording rejection…");
      try {
        const res = await automationValidationApi.finalApproval(memberId, approve, reason ?? undefined);
        toast({
          title: approve ? "Final approval recorded" : "Asset rejected",
          description: `${res.data.decision} · threshold ${res.data.threshold} · score ${res.data.score ?? "—"}`,
        });
        await load();
        await onReload();
      } catch (err) {
        toast({ title: "Decision refused", description: messageFromError(err), variant: "error" });
      } finally {
        setActing(false);
        onBusyChange(null);
      }
    },
    [load, memberId, onBusyChange, onReload, toast],
  );

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 p-6 text-[12px] text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading validation…
      </div>
    );
  }
  if (!data) return null;

  const g = data.gating;
  const decided = g.approval_state !== "PENDING_FINAL";
  const currentStepIndex =
    g.approval_state === "FINAL_APPROVED"
      ? 3
      : g.approval_state === "REJECTED"
        ? 2
        : g.autonomy_state === "AI_APPROVED"
          ? 1
          : 0;

  return (
    <div className="space-y-3">
      {/* Validation summary — four cards. */}
      <Panel
        title="Validation summary"
        action={<span className="text-[10px] text-gray-400">Deterministic results</span>}
      >
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <SummaryCard card={data.cards.static_quality} />
          <SummaryCard card={data.cards.real_execution} />
          <SummaryCard card={data.cards.readiness} />
          <SummaryCard card={data.cards.confidence_score} />
        </div>
      </Panel>

      {/* Gating decision — the MACHINE axis. */}
      <div
        className={cn(
          "rounded-lg border p-3",
          g.autonomy_state === "AI_APPROVED"
            ? "border-emerald-300 bg-emerald-50"
            : "border-amber-300 bg-amber-50",
        )}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-gray-600">
              Gating decision · Autonomy &amp; Scoring Model
            </p>
            <p
              className={cn(
                "mt-0.5 text-[14px] font-bold",
                g.autonomy_state === "AI_APPROVED" ? "text-emerald-800" : "text-amber-900",
              )}
            >
              {g.autonomy_state === "AI_APPROVED"
                ? "AI Approved — advanced automatically"
                : g.autonomy_state === "AI_HELD"
                  ? "AI Held"
                  : "Not yet evaluated"}
            </p>
            <p className="text-[11px] text-gray-700">
              {g.preconditions.filter((p) => p.met).length} of {g.preconditions.length}{" "}
              preconditions met · threshold {g.threshold} · rubric {g.rubric_id}
            </p>
            {g.held_reason ? (
              <p className="mt-0.5 text-[11px] font-medium text-amber-900">{g.held_reason}</p>
            ) : null}
            {!g.enabled ? (
              <p className="mt-1 text-[10px] text-gray-500">
                Automatic approval is disabled for this project, so no autonomy state is written.
                Configuring it is UI-055.
              </p>
            ) : null}
          </div>
          <div className="shrink-0 text-right">
            <p className="text-[9px] font-semibold uppercase tracking-wide text-gray-500">Score</p>
            <p className="text-[22px] font-bold text-gray-900">
              {g.score === null ? "—" : g.score} <span className="text-[12px] text-gray-400">/100</span>
            </p>
          </div>
        </div>

        {/* All five preconditions, always — a reviewer needs the whole picture. */}
        <ul className="mt-2 space-y-0.5 border-t border-white/60 pt-2">
          {g.preconditions.map((p) => (
            <li key={p.code} className="flex items-start gap-1.5 text-[11px]">
              {p.met ? (
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" />
              ) : (
                <CircleSlash className="mt-0.5 h-3 w-3 shrink-0 text-red-600" />
              )}
              <span className={cn(p.met ? "text-gray-700" : "font-medium text-gray-900")}>
                {p.label}
                <span className="ml-1 text-gray-500">— {p.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Validation details — sub-tabs WITHIN one panel, not page navigation. */}
      <Panel title="Validation details">
        <div className="mb-2 flex gap-1 border-b border-gray-100">
          {DETAIL_TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setDetailTab(t)}
              className={cn(
                "-mb-px border-b-2 px-2 py-1 text-[11px] font-semibold",
                detailTab === t
                  ? "border-app-brand-600 text-app-brand-700"
                  : "border-transparent text-gray-500 hover:text-gray-800",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {detailTab === "Static quality" ? (
          <div className="space-y-1">
            {data.findings.length === 0 ? (
              <p className="text-[11px] text-gray-400">
                {data.unavailable.static_quality ?? "No findings."}
              </p>
            ) : (
              data.findings.map((f, i) => (
                <div
                  key={`${f.code}-${i}`}
                  className="flex items-start justify-between gap-2 rounded border border-gray-100 p-1.5"
                >
                  <div className="min-w-0">
                    <p className="flex items-center gap-1 text-[11px] font-semibold text-gray-800">
                      {f.severity === "block" ? (
                        <Ban className="h-3 w-3 text-red-600" />
                      ) : (
                        <AlertTriangle className="h-3 w-3 text-amber-600" />
                      )}
                      {f.code}
                      {f.accepted ? (
                        <Badge variant="outline" className="text-[8px]">
                          exception accepted
                        </Badge>
                      ) : null}
                    </p>
                    <p className="mt-0.5 text-[10px] text-gray-600">{f.message}</p>
                  </div>
                  {f.waivable && !f.accepted ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 shrink-0 text-[10px]"
                      disabled={acting}
                      onClick={() => void handleAccept(f.code)}
                    >
                      Accept exception
                    </Button>
                  ) : f.severity === "block" ? (
                    <span
                      className="shrink-0 text-[9px] font-semibold text-gray-400"
                      title="Blocking violations cannot be waived from this screen — fix the behaviour and recompile."
                    >
                      not waivable
                    </span>
                  ) : null}
                </div>
              ))
            )}
            {/* Three states, never two. */}
            <p className="mt-1 border-t border-gray-100 pt-1 text-[10px] text-gray-600">
              Syntax check:{" "}
              <span
                className={cn(
                  "font-semibold",
                  data.syntax_check.status === "passed"
                    ? "text-emerald-700"
                    : data.syntax_check.status === "failed"
                      ? "text-red-700"
                      : "text-gray-500",
                )}
              >
                {data.syntax_check.status}
              </span>
              {data.syntax_check.status === "skipped" ? (
                <span className="ml-1 text-gray-400">
                  — {data.syntax_check.detail ?? "the check did not run"}
                </span>
              ) : null}
            </p>
          </div>
        ) : null}

        {detailTab === "Execution" ? (
          data.dry_runs.length === 0 ? (
            <p className="text-[11px] text-gray-400">
              {data.unavailable.real_execution ?? "No dry runs recorded."}
            </p>
          ) : (
            <ul className="space-y-1">
              {data.dry_runs.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2 text-[11px]">
                  <span className="truncate text-gray-700">{r.test_name}</span>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                      r.status === "pass"
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-red-50 text-red-700",
                    )}
                  >
                    {r.status}
                  </span>
                </li>
              ))}
            </ul>
          )
        ) : null}

        {detailTab === "Readiness" ? (
          data.readiness_items.length === 0 ? (
            <p className="text-[11px] text-gray-400">
              {data.unavailable.readiness ?? "Nothing unresolved."}
            </p>
          ) : (
            <ul className="space-y-1">
              {data.readiness_items.map((item, i) => (
                <li key={i} className="rounded border border-amber-200 bg-amber-50 p-1.5">
                  <p className="text-[11px] font-semibold text-amber-900">{item.kind}</p>
                  <p className="text-[10px] text-amber-800">{item.detail}</p>
                </li>
              ))}
            </ul>
          )
        ) : null}

        {detailTab === "Confidence" ? (
          Object.keys(g.dimensions).length === 0 ? (
            <p className="text-[11px] text-gray-400">
              {data.unavailable.confidence_score ?? "No score computed."}
            </p>
          ) : (
            <ul className="space-y-1">
              {Object.entries(g.dimensions).map(([name, value]) => (
                <li key={name} className="flex items-center gap-2 text-[11px]">
                  <span className="w-44 shrink-0 text-gray-600">{name.replace(/_/g, " ")}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded bg-gray-100">
                    <span
                      className="block h-full bg-app-brand-500"
                      style={{ width: `${Math.round(value * 100)}%` }}
                    />
                  </span>
                  <span className="w-10 shrink-0 text-right font-medium text-gray-700">
                    {value.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </Panel>

      {/* Approval workflow — the HUMAN axis. No AI_APPROVED node here. */}
      <Panel title="Approval workflow">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] text-gray-500">
              Current state{" "}
              <Badge
                variant={
                  g.approval_state === "FINAL_APPROVED"
                    ? "success"
                    : g.approval_state === "REJECTED"
                      ? "destructive"
                      : "warning"
                }
                className="ml-1 text-[9px]"
              >
                {g.approval_state.replace(/_/g, " ")}
              </Badge>
            </p>
            <p className="mt-0.5 text-[10px] text-gray-500">
              Final approval is mandatory before this suite can be published.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              className="h-7 text-[11px]"
              disabled={acting || decided}
              title={decided ? `Already ${g.approval_state}.` : undefined}
              onClick={() => void handleDecision(true)}
            >
              <ShieldCheck className="mr-1 h-3 w-3" />
              Give final approval
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px]"
              disabled={acting || decided}
              title={decided ? `Already ${g.approval_state}.` : undefined}
              onClick={() => void handleDecision(false)}
            >
              <Send className="mr-1 h-3 w-3" />
              Reject
            </Button>
          </div>
        </div>

        <div className="mt-3 flex items-center">
          {WORKFLOW_STEPS.map((label, i) => (
            <div key={label} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full border text-[9px] font-bold",
                    i <= currentStepIndex
                      ? "border-app-brand-600 bg-app-brand-600 text-white"
                      : "border-gray-300 bg-white text-gray-400",
                  )}
                >
                  {i + 1}
                </div>
                <span
                  className={cn(
                    "mt-0.5 whitespace-nowrap text-[9px]",
                    i <= currentStepIndex ? "font-semibold text-gray-800" : "text-gray-400",
                  )}
                >
                  {label}
                </span>
              </div>
              {i < WORKFLOW_STEPS.length - 1 ? (
                <div
                  className={cn(
                    "mx-1 mb-3 h-px flex-1",
                    i < currentStepIndex ? "bg-app-brand-600" : "bg-gray-200",
                  )}
                />
              ) : null}
            </div>
          ))}
        </div>
      </Panel>

      {/* Decision history — insert-only, stored by value. */}
      <Panel title="Decision history" action={<span className="text-[10px] text-gray-400">{decisions.length}</span>}>
        {decisions.length === 0 ? (
          <p className="text-[11px] text-gray-400">No decisions recorded yet.</p>
        ) : (
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-left text-[9px] uppercase text-gray-400">
                <th className="py-1">Decision</th>
                <th>By</th>
                <th>Score</th>
                <th>Threshold</th>
                <th>Rubric</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((d) => (
                <tr key={d.id} className="border-t border-gray-100">
                  <td className="py-1 font-medium text-gray-800">{d.decision}</td>
                  {/* NULL actor means the machine decided. */}
                  <td className="text-gray-600">{d.decided_by ?? "machine"}</td>
                  <td className="text-gray-600">{d.score ?? "—"}</td>
                  <td className="text-gray-600">{d.threshold}</td>
                  <td className="text-gray-500">{d.rubric_id}</td>
                  <td className="max-w-[200px] truncate text-gray-500">{d.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
