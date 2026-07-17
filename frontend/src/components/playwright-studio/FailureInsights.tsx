"use client";

import { AlertOctagon, AlertTriangle, Info, Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { StudioFailureInsight } from "@/lib/api";

const SEVERITY_STYLE: Record<string, { border: string; icon: React.ReactNode }> = {
  error: {
    border: "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/30",
    icon: <AlertOctagon className="h-4 w-4 shrink-0 text-red-600" />,
  },
  warning: {
    border: "border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30",
    icon: <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />,
  },
  info: {
    border: "border-border bg-muted/30",
    icon: <Info className="h-4 w-4 shrink-0 text-muted-foreground" />,
  },
};

/** Run Diagnostics — actionable non-functional findings derived from the
 * run's failures (environment, infrastructure, routes/auth, test data), so
 * the user knows what THEY need to change vs. what the platform heals. */
export function FailureInsights({ insights }: { insights: StudioFailureInsight[] }) {
  if (!insights || insights.length === 0) return null;
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Lightbulb className="h-4 w-4 text-violet-600" /> Run Diagnostics — what to do next
        </div>
        {insights.map((insight) => {
          const style = SEVERITY_STYLE[insight.severity] ?? SEVERITY_STYLE.info;
          return (
            <div
              key={insight.kind}
              className={cn("flex items-start gap-2 rounded-md border p-3 text-xs", style.border)}
            >
              {style.icon}
              <div className="min-w-0 space-y-1">
                <p className="font-medium">
                  {insight.message}{" "}
                  <Badge variant="outline" className="ml-1">{insight.count} test(s)</Badge>
                </p>
                <p className="text-muted-foreground">
                  <span className="font-semibold text-foreground">Action:</span> {insight.action}
                </p>
                {insight.examples.length > 0 && (
                  <p className="truncate text-[11px] text-muted-foreground">
                    e.g. {insight.examples.join(" · ")}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
