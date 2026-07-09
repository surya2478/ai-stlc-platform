"use client";

import { useState } from "react";
import { ShieldCheck, ShieldAlert, ShieldX, Loader2 } from "lucide-react";
import { reviewsApi, type ArtifactReview } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody,
} from "@/components/ui/drawer";
import { cn } from "@/lib/utils";

function verdictVariant(verdict: string): "success" | "warning" | "destructive" {
  if (verdict === "pass") return "success";
  if (verdict === "needs_revision") return "warning";
  return "destructive";
}

function VerdictIcon({ verdict, className }: { verdict: string; className?: string }) {
  if (verdict === "pass") return <ShieldCheck className={className} />;
  if (verdict === "needs_revision") return <ShieldAlert className={className} />;
  return <ShieldX className={className} />;
}

/**
 * Review verdict badge for a stage-reviewer-covered artifact (Phase 1).
 * Renders nothing when no review exists yet — reviewers are additive, not a
 * required gate in advisory/off mode, so an un-reviewed artifact isn't an error.
 */
export function ReviewBadge({
  review,
  artifactType,
  artifactId,
  projectId,
}: {
  review: ArtifactReview | undefined;
  artifactType: string;
  artifactId: number;
  projectId: number;
}) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<ArtifactReview[] | null>(null);
  const [loading, setLoading] = useState(false);

  if (!review) return null;

  const handleOpen = async () => {
    setOpen(true);
    if (history) return;
    setLoading(true);
    try {
      const res = await reviewsApi.history(artifactType, artifactId, projectId);
      setHistory(res.data);
    } catch {
      setHistory([review]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        className="inline-flex items-center gap-1 rounded transition-opacity hover:opacity-80"
        title="View reviewer findings"
      >
        <VerdictIcon verdict={review.verdict} className="h-3 w-3 shrink-0" />
        <Badge variant={verdictVariant(review.verdict)}>
          {review.overall_score !== undefined && review.overall_score !== null
            ? `${Number(review.overall_score).toFixed(1)}/5`
            : review.verdict.replace(/_/g, " ")}
        </Badge>
      </button>

      <Drawer open={open} onOpenChange={setOpen}>
        <DrawerContent size="lg">
          <DrawerHeader>
            <div>
              <DrawerTitle>Reviewer findings</DrawerTitle>
              <DrawerDescription>{review.reviewer_agent} · {artifactType.replace(/_/g, " ")}</DrawerDescription>
            </div>
          </DrawerHeader>
          <DrawerBody>
            {loading && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading history…
              </div>
            )}
            {(history ?? [review]).map((r) => (
              <div key={r.id} className="rounded-lg border border-slate-200 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <VerdictIcon verdict={r.verdict} className="h-3.5 w-3.5" />
                    <Badge variant={verdictVariant(r.verdict)} className="capitalize">
                      {r.verdict.replace(/_/g, " ")}
                    </Badge>
                    {r.overall_score !== undefined && r.overall_score !== null && (
                      <span className="text-xs font-bold text-slate-600">{Number(r.overall_score).toFixed(1)}/5</span>
                    )}
                  </div>
                  <span className="text-[10px] font-semibold text-slate-400">
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                </div>

                {r.scores && Object.keys(r.scores).length > 0 && (
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(r.scores).map(([dim, score]) => (
                      <div key={dim} className="flex items-center justify-between text-[11px] bg-slate-50 rounded px-2 py-1">
                        <span className="text-slate-500 capitalize">{dim.replace(/_/g, " ")}</span>
                        <span className="font-bold text-slate-700">{Number(score).toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                )}

                {r.coverage_gaps && r.coverage_gaps.length > 0 && (
                  <div>
                    <div className="text-[11px] font-bold text-rose-600 mb-1">Coverage gaps</div>
                    <ul className="space-y-1">
                      {r.coverage_gaps.map((gap, i) => (
                        <li key={i} className={cn(
                          "text-[11px] leading-relaxed rounded px-2 py-1 border",
                          gap.severity === "high" ? "bg-rose-50 border-rose-100 text-rose-700" :
                          gap.severity === "low" ? "bg-slate-50 border-slate-100 text-slate-600" :
                          "bg-amber-50 border-amber-100 text-amber-700"
                        )}>
                          {gap.description}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {r.findings && r.findings.length > 0 && (
                  <div>
                    <div className="text-[11px] font-bold text-slate-600 mb-1">Findings</div>
                    <ul className="space-y-1">
                      {r.findings.map((f, i) => (
                        <li key={i} className="text-[11px] leading-relaxed text-slate-600">
                          <span className="font-bold capitalize">{f.dimension}:</span> {f.issue}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </DrawerBody>
        </DrawerContent>
      </Drawer>
    </>
  );
}
