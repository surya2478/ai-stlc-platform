"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bug, FileText, Loader2, Paperclip, Sparkles, Trash2, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  executionApi,
  type ManualStepResult,
  type ManualStepStatus,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

const STEP_STATUS_OPTIONS: { value: ManualStepStatus; label: string; tone: string }[] = [
  { value: "passed", label: "Passed", tone: "text-emerald-600 hover:bg-emerald-50" },
  { value: "failed", label: "Failed", tone: "text-red-600 hover:bg-red-50" },
  { value: "blocked", label: "Blocked", tone: "text-orange-600 hover:bg-orange-50" },
  { value: "skipped", label: "Skipped", tone: "text-slate-500 hover:bg-slate-50" },
];

// The AI assist endpoint speaks pass/fail/blocked; step statuses use the
// longer forms.
const AI_STATUS_TO_STEP: Record<string, ManualStepStatus> = {
  pass: "passed",
  fail: "failed",
  blocked: "blocked",
};

interface AiSuggestion {
  suggested_status: "pass" | "fail" | "blocked";
  confidence: number;
  reasoning: string;
  observations: string[];
  inputs_used: { mode: "vision" | "text_only"; vision_blocker: string | null };
}

export function StepEditor({
  step,
  testName,
  locked,
  onChange,
  onUpload,
  onDeleteEvidence,
  onDraftDefect,
}: {
  step: ManualStepResult;
  testName: string;
  locked: boolean;
  onChange: (patch: { status?: ManualStepStatus; actual_result?: string; comments?: string }) => void;
  onUpload: (file: File) => void;
  onDeleteEvidence: (evidenceId: string) => void;
  /** Opens a defect draft prefilled from this step (hidden when omitted). */
  onDraftDefect?: () => void;
}) {
  const { toast } = useToast();
  const { runAIAction } = useAIAction();
  const [actual, setActual] = useState(step.actual_result ?? "");
  const [comments, setComments] = useState(step.comments ?? "");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // AI assist state
  const [aiOpen, setAiOpen] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiResult, setAiResult] = useState<AiSuggestion | null>(null);
  const [aiScreenshot, setAiScreenshot] = useState<File | null>(null);
  const aiFileRef = useRef<HTMLInputElement>(null);

  // Evidence lightbox
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  // Reset local state when step changes. Also flush any pending debounced
  // save FIRST so we don't write the previous step's text onto the new step.
  const debouncedSave = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (debouncedSave.current) {
      clearTimeout(debouncedSave.current);
      debouncedSave.current = null;
    }
    setActual(step.actual_result ?? "");
    setComments(step.comments ?? "");
    setAiOpen(false);
    setAiResult(null);
    setAiScreenshot(null);
    setLightboxUrl(null);
  }, [step.id, step.actual_result, step.comments]);

  // Cancel any pending save on unmount to avoid setState-after-unmount.
  useEffect(() => () => {
    if (debouncedSave.current) clearTimeout(debouncedSave.current);
  }, []);

  const scheduleSave = (patch: { actual_result?: string; comments?: string }) => {
    if (debouncedSave.current) clearTimeout(debouncedSave.current);
    debouncedSave.current = setTimeout(() => onChange(patch), 600);
  };

  const runAiAssist = async () => {
    setAiBusy(true);
    setAiResult(null);
    try {
      const res = await runAIAction({
        actionName: "analyze_manual_execution_step",
        title: "Analyzing Execution Evidence",
        module: "Manual Execution",
        artifactType: "Step Recommendation",
        stages: AI_PROCESSING_STAGES.failureDiagnosis,
        successMessage: "Execution-step recommendation is ready.",
        execute: () => executionApi.aiAssistStep(step.id, {
          actualResult: actual || undefined,
          comments: comments || undefined,
          screenshot: aiScreenshot ?? undefined,
        }),
      });
      setAiResult(res.data as AiSuggestion);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "AI assist unavailable",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "warning",
      });
    } finally {
      setAiBusy(false);
    }
  };

  const applyAiSuggestion = () => {
    if (!aiResult) return;
    const mapped = AI_STATUS_TO_STEP[aiResult.suggested_status];
    if (mapped) onChange({ status: mapped });
    setAiResult(null);
    setAiOpen(false);
  };

  const imageEvidence = step.evidence.filter((ev) => (ev.content_type ?? "").startsWith("image/"));
  const fileEvidence = step.evidence.filter((ev) => !(ev.content_type ?? "").startsWith("image/"));

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-slate-50 px-3 py-2">
        <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Step {step.step_number} — {testName}</p>
        <p className="text-xs text-slate-700 mt-1 whitespace-pre-line">{step.action_text ?? "(no action recorded)"}</p>
        {step.expected_text && (
          <p className="mt-2 text-[11px] text-slate-600">
            <span className="font-semibold text-slate-500">Expected: </span>{step.expected_text}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] font-semibold text-slate-600 mb-1">Outcome</label>
          <div className="grid grid-cols-2 gap-1">
            {STEP_STATUS_OPTIONS.map((opt) => {
              const active = step.status === opt.value;
              return (
                <button
                  key={opt.value}
                  disabled={locked}
                  onClick={() => onChange({ status: opt.value })}
                  className={cn(
                    "rounded border px-2 py-1.5 text-[11px] font-semibold transition-colors",
                    active ? "border-[#1b59f8] bg-[#1b59f8] text-white" : `border-slate-200 ${opt.tone}`,
                    locked && "opacity-50 cursor-not-allowed"
                  )}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <label className="block text-[11px] font-semibold text-slate-600 mb-1">Time Taken</label>
          <p className="text-xs text-slate-500">{step.started_at ? `Started ${formatDate(step.started_at)}` : "Not started"}</p>
          {step.completed_at && <p className="text-[11px] text-slate-400">Completed {formatDate(step.completed_at)}</p>}
        </div>
      </div>

      {/* AI assist + defect actions */}
      {!locked && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setAiOpen((v) => !v)}
            className="gap-1.5 border-violet-200 text-xs text-violet-700 hover:bg-violet-50"
          >
            <Sparkles className="h-3.5 w-3.5" /> AI suggest
          </Button>
          {onDraftDefect && step.status === "failed" && (
            <Button
              size="sm"
              variant="outline"
              onClick={onDraftDefect}
              className="gap-1.5 border-red-200 text-xs text-red-700 hover:bg-red-50"
            >
              <Bug className="h-3.5 w-3.5" /> Draft defect
            </Button>
          )}
        </div>
      )}

      {aiOpen && !locked && (
        <div className="space-y-2 rounded-lg border border-violet-200 bg-violet-50/40 p-3">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-semibold text-violet-800">
              Ask AI for a pass/fail suggestion based on this step&apos;s text
              {aiScreenshot ? ` + screenshot (${aiScreenshot.name})` : ""}
            </p>
            <button onClick={() => { setAiOpen(false); setAiResult(null); }} className="text-violet-400 hover:text-violet-700">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => aiFileRef.current?.click()}
              className="inline-flex items-center gap-1 rounded-md border border-violet-200 bg-white px-2 py-1 text-[11px] text-violet-700 hover:bg-violet-50"
            >
              <Paperclip className="h-3 w-3" />
              {aiScreenshot ? "Change screenshot" : "Attach screenshot (optional)"}
            </button>
            <input
              ref={aiFileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                setAiScreenshot(e.target.files?.[0] ?? null);
                e.target.value = "";
              }}
            />
            <Button size="sm" onClick={runAiAssist} disabled={aiBusy} className="gap-1.5 bg-violet-600 text-xs text-white hover:bg-violet-700">
              {aiBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
              Analyze
            </Button>
          </div>

          {aiResult && (
            <div className="rounded-md border border-violet-200 bg-white p-3">
              <div className="flex items-center gap-2">
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase",
                  aiResult.suggested_status === "pass" && "bg-emerald-100 text-emerald-700",
                  aiResult.suggested_status === "fail" && "bg-red-100 text-red-700",
                  aiResult.suggested_status === "blocked" && "bg-orange-100 text-orange-700",
                )}>
                  {aiResult.suggested_status}
                </span>
                <span className="text-[11px] text-slate-500">
                  Confidence <b className="tabular-nums">{aiResult.confidence}%</b>
                  {aiResult.inputs_used.mode === "text_only" && aiResult.inputs_used.vision_blocker && (
                    <span className="ml-1 text-slate-400">(text-only: {aiResult.inputs_used.vision_blocker})</span>
                  )}
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-slate-700">{aiResult.reasoning}</p>
              {aiResult.observations.length > 0 && (
                <ul className="mt-1 list-inside list-disc text-[11px] text-slate-500">
                  {aiResult.observations.map((o, i) => <li key={i}>{o}</li>)}
                </ul>
              )}
              <div className="mt-2 flex items-center gap-2">
                <Button size="sm" onClick={applyAiSuggestion} className="h-6 px-2 text-[10px]">
                  Apply status
                </Button>
                <Button size="sm" variant="outline" onClick={() => setAiResult(null)} className="h-6 px-2 text-[10px]">
                  Dismiss
                </Button>
                <span className="text-[10px] text-slate-400">You stay in control — AI only suggests.</span>
              </div>
            </div>
          )}
        </div>
      )}

      <div>
        <label className="block text-[11px] font-semibold text-slate-600 mb-1">Actual Result</label>
        <textarea
          rows={2}
          value={actual}
          disabled={locked}
          onChange={(e) => { setActual(e.target.value); scheduleSave({ actual_result: e.target.value }); }}
          placeholder="What did you observe?"
          className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#1b59f8] disabled:bg-slate-50 disabled:text-slate-500"
        />
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-slate-600 mb-1">Comments / Tester Notes</label>
        <textarea
          rows={2}
          value={comments}
          disabled={locked}
          onChange={(e) => { setComments(e.target.value); scheduleSave({ comments: e.target.value }); }}
          placeholder="Optional context — defects, env notes, screenshot annotations"
          className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#1b59f8] disabled:bg-slate-50 disabled:text-slate-500"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-[11px] font-semibold text-slate-600">Evidence ({step.evidence.length})</label>
          {!locked && (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-[11px] text-[#1b59f8] hover:underline flex items-center gap-1"
            >
              <Paperclip className="h-3 w-3" /> Upload
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              e.target.value = "";
            }}
          />
        </div>

        {step.evidence.length === 0 ? (
          <p className="text-[11px] text-slate-400 px-3 py-2 border border-dashed border-slate-200 rounded">No evidence attached</p>
        ) : (
          <div className="space-y-2">
            {/* Image gallery */}
            {imageEvidence.length > 0 && (
              <div className="grid grid-cols-4 gap-2">
                {imageEvidence.map((ev) => (
                  <div key={ev.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => setLightboxUrl(ev.download_url)}
                      className="block w-full overflow-hidden rounded-md border border-slate-200"
                      title={ev.filename}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={ev.download_url}
                        alt={ev.filename}
                        loading="lazy"
                        className="h-16 w-full object-cover transition-transform group-hover:scale-105"
                      />
                    </button>
                    {!locked && (
                      <button
                        onClick={() => onDeleteEvidence(ev.id)}
                        className="absolute -right-1.5 -top-1.5 hidden rounded-full bg-white p-0.5 text-slate-400 shadow ring-1 ring-slate-200 hover:text-red-600 group-hover:block"
                        aria-label="Delete evidence"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
            {/* Non-image files */}
            {fileEvidence.map((ev) => (
              <div key={ev.id} className="flex items-center justify-between gap-2 rounded border border-slate-100 px-2 py-1 text-[11px]">
                <a href={ev.download_url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-slate-700 hover:text-[#1b59f8] truncate">
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{ev.filename}</span>
                  <span className="text-slate-400">({Math.ceil(ev.size / 1024)} KB)</span>
                </a>
                {!locked && (
                  <button
                    onClick={() => onDeleteEvidence(ev.id)}
                    className="text-slate-400 hover:text-red-600"
                    aria-label="Delete evidence"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Lightbox */}
      {lightboxUrl && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-6"
          onClick={() => setLightboxUrl(null)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={lightboxUrl}
            alt="Evidence preview"
            className="max-h-full max-w-full rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
            onClick={() => setLightboxUrl(null)}
            aria-label="Close preview"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      )}
    </div>
  );
}
