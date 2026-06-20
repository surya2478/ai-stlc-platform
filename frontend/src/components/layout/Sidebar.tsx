"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import {
  LayoutDashboard, FileText, ClipboardList,
  TestTube2, Code2, Play, Bug, BarChart3, Settings,
  Bot, ChevronRight, Cpu, Users, Database,
  ChevronLeft, Menu, Activity, ShieldAlert, Sliders, Bell,
  Brain, BookOpen, ShieldCheck, ClipboardCheck
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  {
    group: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    ],
  },
  {
    group: "STLC Pipeline",
    items: [
      { label: "Requirements", href: "/requirements", icon: FileText },
      { label: "Test Planning", href: "/test-planning", icon: ClipboardList },
      { label: "Test Cases", href: "/test-cases", icon: TestTube2 },
      { label: "Test Data", href: "/test-data", icon: Database },
      { label: "Automation", href: "/automation", icon: Code2 },
      { label: "Execution", href: "/execution", icon: Play },
      { label: "Defects", href: "/defects", icon: Bug },
      { label: "Reports", href: "/reports", icon: BarChart3 },
    ],
  },
  {
    group: "Intelligence",
    items: [
      { label: "AI Quality Intelligence", href: "/agents", icon: Brain },
      { label: "RAG Knowledge", href: "/agents/logs", icon: BookOpen },
    ],
  },
  {
    group: "Operations",
    items: [
      { label: "AI Agents", href: "/agents", icon: Bot },
      { label: "Approvals", href: "/requirements", icon: ClipboardCheck },
    ],
  },
  {
    group: "Settings",
    items: [
      { label: "Project Settings", href: "/settings", icon: Settings },
      { label: "Users & Roles", href: "/users", icon: Users },
    ],
  },
];

function SidebarContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");
  
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem("sidebar-collapsed");
    if (saved) {
      setCollapsed(saved === "true");
    }
  }, []);

  const toggleCollapse = () => {
    const nextState = !collapsed;
    setCollapsed(nextState);
    localStorage.setItem("sidebar-collapsed", String(nextState));
  };

  if (!mounted) {
    return <aside className="flex w-60 flex-col bg-[#091225] border-r border-[#13223f] text-slate-400" />;
  }

  return (
    <aside 
      className={cn(
        "flex flex-col border-r border-[#13223f] bg-[#091225] text-slate-400 transition-all duration-300 ease-in-out select-none",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 border-b border-[#13223f] px-4 overflow-hidden shrink-0">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-cyan-400 to-indigo-500 shadow-md">
          <Bot className="h-4.5 w-4.5 text-white" />
        </div>
        {!collapsed && (
          <div className="flex flex-col min-w-0 transition-opacity duration-300">
            <span className="font-bold text-sm text-white leading-tight tracking-wide truncate">
              AI STLC Platform
            </span>
            <span className="text-[10px] font-medium text-cyan-400 tracking-wider uppercase leading-none mt-0.5">
              Command Center
            </span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 space-y-4 no-scrollbar">
        {NAV_ITEMS.map((group) => (
          <div key={group.group} className="px-2">
            {!collapsed ? (
              <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                {group.group}
              </p>
            ) : (
              <div className="border-t border-[#13223f]/50 my-3 first:hidden" />
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(item.href + "/");
                const hrefWithProject = projectId ? `${item.href}?project=${projectId}` : item.href;
                return (
                  <Link
                    key={item.href}
                    href={hrefWithProject}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-all duration-150",
                      active
                        ? "bg-[#1b59f8] text-white shadow-sm"
                        : "text-slate-400 hover:bg-[#13223f] hover:text-white"
                    )}
                  >
                    <item.icon className={cn("h-4 w-4 shrink-0", active ? "text-white" : "text-slate-400")} />
                    {!collapsed && (
                      <span className="truncate flex-1">{item.label}</span>
                    )}
                    {!collapsed && active && <ChevronRight className="ml-auto h-3 w-3 opacity-60" />}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer / Collapse Button */}
      <div className="border-t border-[#13223f] p-3 flex items-center justify-between shrink-0">
        {!collapsed && (
          <p className="text-[10px] text-slate-500 font-mono pl-1">v1.0.0 — Enterprise</p>
        )}
        <button
          onClick={toggleCollapse}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#13223f] hover:bg-[#13223f] hover:text-white transition-colors ml-auto"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
    </aside>
  );
}

export function Sidebar() {
  return (
    <Suspense fallback={<aside className="flex w-60 flex-col bg-[#091225] border-r border-[#13223f] text-slate-400" />}>
      <SidebarContent />
    </Suspense>
  );
}
