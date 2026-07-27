"use client";

// UI-019 Live Recorder — Section 21's recording summary, shown before saving.
//
// Figures that have no real source render as an explained dash rather than a
// zero (see `MeasureValue`): "0 console errors" and "console was never
// captured" are different answers, and only one of them is safe to act on.

import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileWarning,
  Loader2,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import type { AutomationIrDraft, RecordingSummary } from "@/lib/api";
import { cn } from "@/lib/utils";
import { messageFromError } from "@/components/automation/suite-shared";
import { MeasureValue, formatDuration } from "@/components/automation/recorder-shared";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summary: RecordingSummary | undefined;
  irDraft: AutomationIrDraft | null | undefined;
  loading: boolean;
  canEmitIr: boolean;
  onEmitIr: () => Promise<unknown>;
  onDiscard: (reason: string) => Promise<unknown>;
}

export function RecordingSummaryDrawer({
  open,
  onOpenChange,
  summary,
  irDraft,
  loading,
  canEmitIr,
  onEmitIr,
  onDiscard,
}: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"ir" | "discard" | null>(null);
  const [discardReason, setDiscardReason] = useState("");
  const [showDiscard, setShowDiscard] = useState(false);

  const run = async (kind: "ir" | "discard", fn: () => Promise<unknown>) => {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      if (kind === "discard") onOpenChange(false);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setBusy(null);
    }
  };

  const coverage = summary?.test_case_coverage;

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent size="2xl">
        <DrawerHeader>
          <DrawerTitle>Recording Summary</DrawerTitle>
          <DrawerDescription>
            What this recording captured, and what is still open. Review before converting to Automation IR.
          </DrawerDescription>
        </DrawerHeader>

        <DrawerBody>
          {loading || !summary ? (
            <p className="p-4 text-xs font-semibold text-slate-400">Building summary…</p>
          ) : (
            <div className="space-y-4">
              {error && (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-bold text-red-700">
                  {error}
                </p>
              )}

              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Metric label="Duration" value={formatDuration(summary.duration_seconds)} />
                <Metric label="Actions" value={summary.recorded_actions} />
                <Metric
                  label="Step coverage"
                  value={coverage?.percent === null ? "—" : `${coverage?.percent}%`}
                  hint={coverage?.percent_basis}
                />
                <Metric label="Checkpoints" value={summary.checkpoints.accepted} hint="Accepted" />
              </div>

              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <MeasureMetric label="Network requests" measure={summary.network_requests} />
                <MeasureMetric label="Network failures" measure={summary.network_failures} />
                <MeasureMetric label="Console errors" measure={summary.console_errors} />
                <MeasureMetric label="Console warnings" measure={summary.console_warnings} />
              </div>

              <Section title="Coverage">
                <ul className="space-y-0.5 text-[11px] font-semibold text-slate-600">
                  <li>{coverage?.recorded_steps} step(s) have recorded actions</li>
                  <li>{coverage?.steps_without_actions} step(s) have nothing recorded</li>
                  <li>{coverage?.skipped_steps} step(s) deliberately skipped (excluded from the percentage)</li>
                </ul>
              </Section>

              <GapList
                title="Steps with nothing recorded"
                items={summary.missing_steps.map((step) => `${step.step_key} — ${step.action_text ?? ""}`)}
                emptyMessage="Every step has at least one recorded action."
              />
              <GapList
                title="Actions not mapped to a step"
                items={summary.unmapped_actions.map(
                  (action) => `#${action.sequence} ${action.action_family} — ${action.target_semantic ?? ""}`,
                )}
                emptyMessage="Every recorded action is mapped to a step."
              />
              <GapList
                title="Expected results with no accepted checkpoint"
                items={summary.expected_results_without_checkpoints.map(
                  (row) => `${row.step_key} — ${row.expected_result ?? ""}`,
                )}
                emptyMessage="Every expected result has a checkpoint."
              />
              <GapList
                title="Locator warnings"
                items={summary.locator_warnings.map((row) => `#${row.sequence} — ${row.detail}`)}
                emptyMessage="No low-confidence locators."
              />
              <GapList
                title="Inputs not classified as data"
                items={summary.unbound_inputs.map(
                  (row) =>
                    `#${row.sequence} ${row.target_semantic ?? ""}${
                      row.requires_secret_reference
                        ? " — value was redacted; needs a secret reference"
                        : ""
                    }`,
                )}
                emptyMessage="Every typed value is classified."
              />
              <GapList
                title="Unsupported actions"
                items={summary.unsupported_actions.map((row) => row.detail ?? "")}
                emptyMessage="No action was refused by the adapter."
              />

              <Section title="Evidence">
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(summary.evidence_generated).length === 0 ? (
                    <span className="text-[11px] font-semibold text-slate-400">
                      No evidence captured.
                    </span>
                  ) : (
                    Object.entries(summary.evidence_generated).map(([type, count]) => (
                      <Badge key={type} variant="secondary" className="text-[9px]">
                        {type.replace("_", " ")} · {count}
                      </Badge>
                    ))
                  )}
                </div>
                <p className="mt-1.5 text-[10px] font-semibold text-slate-500">
                  {summary.redactions.inputs} input value(s) and {summary.redactions.captures} capture(s)
                  were redacted before being stored.
                </p>
              </Section>

              <Section title="Applications visited">
                {summary.applications_visited.length === 0 ? (
                  <p className="text-[11px] font-semibold text-slate-400">No segment recorded.</p>
                ) : (
                  <ul className="space-y-0.5 text-[11px] font-semibold text-slate-600">
                    {summary.applications_visited.map((segment) => (
                      <li key={segment.segment}>
                        Segment {segment.segment} — application {segment.application_id} ({segment.environment})
                        {segment.transition_reason ? ` · ${segment.transition_reason}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              {irDraft && (
                <Section title={`Automation IR draft v${irDraft.version}`}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant="purple" className="text-[9px]">
                      {irDraft.readiness.step_count} step(s)
                    </Badge>
                    <Badge variant="secondary" className="text-[9px]">
                      {irDraft.readiness.assertion_count} assertion(s)
                    </Badge>
                    {irDraft.readiness.custom_step_count > 0 && (
                      <Badge variant="warning" className="text-[9px]">
                        {irDraft.readiness.custom_step_count} manual step(s)
                      </Badge>
                    )}
                    <Badge
                      variant={irDraft.readiness.ready_for_script_generation ? "success" : "warning"}
                      className="text-[9px]"
                    >
                      {irDraft.readiness.ready_for_script_generation
                        ? "Ready for script generation"
                        : `${irDraft.readiness.unresolved_count} open item(s)`}
                    </Badge>
                  </div>
                  {irDraft.readiness.unresolved.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {irDraft.readiness.unresolved.map((item, index) => (
                        <li
                          key={`${item.kind}-${index}`}
                          className="flex items-start gap-1.5 text-[10px] font-semibold text-amber-700"
                        >
                          <FileWarning className="mt-0.5 h-3 w-3 shrink-0" />
                          {item.detail}
                        </li>
                      ))}
                    </ul>
                  )}
                </Section>
              )}

              {showDiscard && (
                <Section title="Discard this recording">
                  <p className="mb-1.5 text-[10px] font-semibold text-slate-500">
                    The captured actions and evidence are kept and the recording is marked discarded, so
                    the decision stays reviewable. A reason is required.
                  </p>
                  <input
                    value={discardReason}
                    onChange={(event) => setDiscardReason(event.target.value)}
                    placeholder="Why is this recording being discarded?"
                    className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold focus:outline-none focus:ring-2 focus:ring-red-400"
                  />
                </Section>
              )}
            </div>
          )}
        </DrawerBody>

        <DrawerFooter>
          <div className="flex w-full items-center justify-between gap-2">
            {showDiscard ? (
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={!discardReason.trim() || busy !== null}
                  onClick={() => run("discard", () => onDiscard(discardReason))}
                >
                  {busy === "discard" ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="mr-1 h-3 w-3" />
                  )}
                  Confirm discard
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setShowDiscard(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => setShowDiscard(true)}>
                <Trash2 className="mr-1 h-3 w-3" />
                Discard recording
              </Button>
            )}

            <Button
              size="sm"
              disabled={!canEmitIr || busy !== null}
              title={
                canEmitIr
                  ? "Convert this recording into a framework-neutral Automation IR draft."
                  : "Stop the recording first — an IR can only be emitted from a captured recording."
              }
              onClick={() => run("ir", onEmitIr)}
            >
              {busy === "ir" ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : irDraft ? (
                <CheckCircle2 className="mr-1 h-3 w-3" />
              ) : (
                <ArrowRight className="mr-1 h-3 w-3" />
              )}
              {irDraft ? "Re-generate Automation IR" : "Save & Create Automation IR"}
            </Button>
          </div>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2.5" title={hint}>
      <p className="text-[9px] font-bold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-extrabold leading-none text-slate-950">{value}</p>
    </div>
  );
}

function MeasureMetric({
  label,
  measure,
}: {
  label: string;
  measure: RecordingSummary["network_requests"];
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2.5">
      <p className="text-[9px] font-bold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-lg leading-none">
        <MeasureValue measure={measure} />
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h4 className="mb-1.5 text-[10px] font-extrabold uppercase tracking-wide text-slate-800">{title}</h4>
      {children}
    </section>
  );
}

function GapList({
  title,
  items,
  emptyMessage,
}: {
  title: string;
  items: string[];
  emptyMessage: string;
}) {
  return (
    <Section title={title}>
      {items.length === 0 ? (
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-600">
          <CheckCircle2 className="h-3 w-3" />
          {emptyMessage}
        </p>
      ) : (
        <ul className="space-y-0.5">
          {items.map((item, index) => (
            <li
              key={index}
              className={cn("flex items-start gap-1.5 text-[11px] font-semibold text-amber-700")}
            >
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              {item}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
