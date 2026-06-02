"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FolderOpen, FileText, ClipboardList,
  TestTube2, Code2, Play, Bug, BarChart3, Settings,
  Bot, ChevronRight, Cpu,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  {
    group: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Projects", href: "/projects", icon: FolderOpen },
    ],
  },
  {
    group: "STLC Pipeline",
    items: [
      { label: "Requirements", href: "/requirements", icon: FileText },
      { label: "Test Planning", href: "/test-planning", icon: ClipboardList },
      { label: "Test Cases", href: "/test-cases", icon: TestTube2 },
      { label: "Automation", href: "/automation", icon: Code2 },
      { label: "Execution", href: "/execution", icon: Play },
      { label: "Defects", href: "/defects", icon: Bug },
      { label: "Reports", href: "/reports", icon: BarChart3 },
    ],
  },
  {
    group: "Agents",
    items: [
      { label: "Agent Workflow", href: "/agents", icon: Bot },
      { label: "Agent Logs", href: "/agents/logs", icon: Cpu },
    ],
  },
  {
    group: "System",
    items: [
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 flex-col border-r bg-card">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <Bot className="h-4 w-4 text-primary-foreground" />
        </div>
        <span className="font-semibold text-sm leading-tight">
          STLC AI<br />
          <span className="text-xs font-normal text-muted-foreground">Automation Platform</span>
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4">
        {NAV_ITEMS.map((group) => (
          <div key={group.group} className="mb-4">
            <p className="mb-1 px-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.group}
            </p>
            {group.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-md mx-2 px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                  {active && <ChevronRight className="ml-auto h-3 w-3" />}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t p-4">
        <p className="text-xs text-muted-foreground">v0.1.0 — Phase 1</p>
      </div>
    </aside>
  );
}
