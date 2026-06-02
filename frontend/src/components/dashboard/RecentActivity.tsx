"use client";

import { Activity } from "lucide-react";

export function RecentActivity() {
  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="h-4 w-4 text-primary" />
        <h3 className="font-semibold text-sm">Recent Activity</h3>
      </div>
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <Activity className="h-8 w-8 text-muted-foreground/30 mb-3" />
        <p className="text-sm text-muted-foreground">No activity yet.</p>
        <p className="text-xs text-muted-foreground mt-1">
          Create a project and run your first agent to get started.
        </p>
      </div>
    </div>
  );
}
