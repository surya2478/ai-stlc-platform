"use client";

import { LucideIcon, Construction } from "lucide-react";

interface ComingSoonProps {
  title: string;
  description: string;
  phase: string;
  icon?: LucideIcon;
}

export function ComingSoon({ title, description, phase, icon: Icon = Construction }: ComingSoonProps) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground mt-1">{description}</p>
      </div>
      <div className="rounded-xl border border-dashed bg-card p-16 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
          <Icon className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="font-semibold text-lg mb-2">Coming in {phase}</h3>
        <p className="text-sm text-muted-foreground max-w-md mx-auto">
          This module is part of the AI Agent STLC pipeline and will be fully functional once {phase} implementation is complete.
        </p>
        <div className="mt-6 inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5 text-xs font-medium text-primary">
          <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
          Planned — Phase roadmap active
        </div>
      </div>
    </div>
  );
}
