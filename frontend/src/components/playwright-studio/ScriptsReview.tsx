"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, Loader2, PlayCircle, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import type { StudioRunDetail, StudioScriptSummary } from "@/lib/api";
import { useApproveStudioScripts } from "@/lib/queries/playwrightStudio";
import { runnerIsContainerised, runnerModeLabel } from "./studio-utils";

function scriptStatusVariant(status: string): "success" | "warning" | "destructive" | "outline" | "info" {
  if (["dry_run_passed", "static_passed", "approved"].includes(status)) return "success";
  if (["generated", "mcp_discovered"].includes(status)) return "info";
  if (["needs_regeneration", "rejected"].includes(status)) return "destructive";
  return "warning";
}

function qualityFlags(script: StudioScriptSummary): string[] {
  const flags: string[] = [];
  if (script.grounding && script.grounding.grounded === false) flags.push("ungrounded locators");
  if (script.static_gate_passed === false) flags.push("static gate warnings");
  const dryRun = script.last_dry_run as { passed?: boolean } | null | undefined;
  if (dryRun && dryRun.passed === false) flags.push("dry run failed");
  return flags;
}

/** Step 3 — Generated Tests. Every script with its quality signals
 * (grounding / static gate / dry run) and ONE bulk gate: scripts with known
 * issues require an override note, mirroring the existing bulk-approve rule. */
export function ScriptsReview({
  projectId,
  run,
}: {
  projectId: number | null;
  run: StudioRunDetail;
}) {
  const { toast } = useToast();
  const approveScripts = useApproveStudioScripts(projectId);
  const [notes, setNotes] = useState("");

  const flagged = useMemo(
    () => run.scripts.filter((s) => qualityFlags(s).length > 0),
    [run.scripts],
  );
  const requiresNote = flagged.length > 0 && !notes.trim();

  async function handleApprove() {
    try {
      const result = await approveScripts.mutateAsync({ runId: run.id, notes: notes.trim() || undefined });
      toast({ title: "Scripts approved — execution started", description: result.message });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({
        title: "Could not approve scripts",
        description: typeof detail === "string" ? detail : "Unknown error",
        variant: "error",
      });
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 p-4 text-sm">
          <span className="font-semibold">Generated Scripts</span>
          <span className="text-muted-foreground">{run.scripts.length} script(s)</span>
          {Object.entries(run.script_counts).map(([status, count]) => (
            <Badge key={status} variant={scriptStatusVariant(status)}>
              {status.replaceAll("_", " ")}: {count}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Script</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Version</th>
                  <th className="px-3 py-2 font-medium">Grounding</th>
                  <th className="px-3 py-2 font-medium">Static Gate</th>
                  <th className="px-3 py-2 font-medium">Dry Run</th>
                </tr>
              </thead>
              <tbody>
                {run.scripts.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                      <Loader2 className="mx-auto mb-1 h-4 w-4 animate-spin" />
                      Scripts are still being generated…
                    </td>
                  </tr>
                )}
                {run.scripts.map((script) => {
                  const dryRun = script.last_dry_run as { passed?: boolean } | null | undefined;
                  return (
                    <tr key={script.id} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-2 font-medium">{script.script_id}</td>
                      <td className="px-3 py-2">
                        <Badge variant={scriptStatusVariant(script.status)}>
                          {script.status.replaceAll("_", " ")}
                        </Badge>
                      </td>
                      <td className="px-3 py-2">v{script.version}</td>
                      <td className="px-3 py-2">
                        {script.grounding == null ? (
                          <span className="text-muted-foreground">—</span>
                        ) : script.grounding.grounded ? (
                          <Badge variant="success">grounded</Badge>
                        ) : (
                          <Badge variant="warning">
                            {(script.grounding.ungrounded_elements ?? []).length || "?"} unmatched
                          </Badge>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {script.static_gate_passed == null ? (
                          <span className="text-muted-foreground">—</span>
                        ) : script.static_gate_passed ? (
                          <Badge variant="success">passed</Badge>
                        ) : (
                          <Badge variant="warning">warnings</Badge>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {dryRun == null ? (
                          <span className="text-muted-foreground">pending</span>
                        ) : dryRun.passed ? (
                          <Badge variant="success">passed</Badge>
                        ) : (
                          <Badge variant="destructive">failed</Badge>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 p-4">
          {flagged.length > 0 && (
            <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                {flagged.length} script(s) have known issues ({flagged.map((s) => s.script_id).slice(0, 5).join(", ")}
                {flagged.length > 5 ? "…" : ""}). Bulk-approving them requires an override note explaining why —
                it is recorded on every approval audit entry.
              </span>
            </div>
          )}
          <input
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
            placeholder={flagged.length > 0 ? "Override note (required) *" : "Bulk approval note (optional)"}
            value={notes}
            maxLength={2000}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Approves all {run.scripts.length} script(s) in one action and launches
              {" "}{runnerIsContainerised(run.config.runner_mode)
                ? `${runnerModeLabel(run.config.runner_mode)} execution (${run.config.parallelism ?? 1} parallel containers)`
                : "local execution"} on {run.config.environment}.
            </p>
            <Button
              onClick={handleApprove}
              disabled={run.scripts.length === 0 || requiresNote || approveScripts.isPending}
            >
              {approveScripts.isPending
                ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                : <PlayCircle className="mr-2 h-4 w-4" />}
              Approve All & Execute
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
