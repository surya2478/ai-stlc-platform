"use client";

import { Bot, CheckCircle2, Clock, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const AGENTS = [
  { name: "Requirement Intake", status: "idle" },
  { name: "Requirement Quality", status: "idle" },
  { name: "Test Planning", status: "idle" },
  { name: "Test Scenario", status: "idle" },
  { name: "Test Case Dev", status: "idle" },
  { name: "Test Data", status: "idle" },
  { name: "Automation Script", status: "idle" },
  { name: "Test Execution", status: "idle" },
  { name: "Defect Analysis", status: "idle" },
  { name: "Jira Defect", status: "idle" },
  { name: "Test Reporting", status: "idle" },
];

const STATUS_CONFIG = {
  idle: { icon: Clock, color: "text-muted-foreground", dot: "bg-muted-foreground" },
  running: { icon: Loader2, color: "text-blue-500", dot: "bg-blue-500" },
  completed: { icon: CheckCircle2, color: "text-green-500", dot: "bg-green-500" },
  failed: { icon: XCircle, color: "text-red-500", dot: "bg-red-500" },
};

export function AgentStatusWidget() {
  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm h-full">
      <div className="flex items-center gap-2 mb-4">
        <Bot className="h-4 w-4 text-primary" />
        <h3 className="font-semibold text-sm">Agent Status</h3>
      </div>
      <div className="space-y-2">
        {AGENTS.map((agent) => {
          const cfg = STATUS_CONFIG[agent.status as keyof typeof STATUS_CONFIG];
          return (
            <div key={agent.name} className="flex items-center gap-2.5">
              <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", cfg.dot)} />
              <span className="text-xs text-muted-foreground flex-1 truncate">{agent.name}</span>
              <span className="text-xs text-muted-foreground capitalize">{agent.status}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
