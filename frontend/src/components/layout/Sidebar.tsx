"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import {
  LayoutDashboard, FileText, ClipboardList,
  TestTube2, Play, Bug, BarChart3, Settings,
  Bot, ChevronRight, ChevronDown, Users, Database,
  ChevronLeft, Brain, BookOpen,
  Hand, Cpu, Sparkles, Gauge, Table2,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  children?: NavItem[];
};

type NavGroup = {
  group: string;
  items: NavItem[];
};

const NAV_ITEMS: NavGroup[] = [
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
      { label: "AI Automation Studio", href: "/automation", icon: Sparkles },
      {
        label: "Execution",
        href: "/execution",
        icon: Play,
        children: [
          { label: "Manual Execution", href: "/execution/manual", icon: Hand },
          { label: "Automation Execution", href: "/execution/automation", icon: Cpu },
          { label: "Execution Dashboard", href: "/execution/dashboard", icon: Gauge },
        ],
      },
      { label: "Defects", href: "/defects", icon: Bug },
      { label: "Reports", href: "/reports", icon: BarChart3 },
      { label: "Coverage Matrix", href: "/coverage-matrix", icon: Table2 },
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
      { label: "Resource Intelligence", href: "/resource-intelligence", icon: Users },
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

const EXPANDED_STORAGE_KEY = "sidebar-expanded-items";

function withProject(href: string, projectId: string | null): string {
  return projectId ? `${href}?project=${projectId}` : href;
}

function isActiveHref(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + "/");
}

function isParentActive(pathname: string, item: NavItem): boolean {
  if (isActiveHref(pathname, item.href)) return true;
  return Boolean(item.children?.some((c) => isActiveHref(pathname, c.href)));
}

function SidebarContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setMounted(true);
    const savedCollapsed = localStorage.getItem("sidebar-collapsed");
    if (savedCollapsed) setCollapsed(savedCollapsed === "true");
    const savedExpanded = localStorage.getItem(EXPANDED_STORAGE_KEY);
    if (savedExpanded) {
      try {
        setExpanded(JSON.parse(savedExpanded));
      } catch {
        /* ignore */
      }
    }
  }, []);

  useEffect(() => {
    if (!mounted) return;
    // Auto-expand any parent whose child matches the current route
    setExpanded((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const group of NAV_ITEMS) {
        for (const item of group.items) {
          if (item.children && isParentActive(pathname, item) && !next[item.href]) {
            next[item.href] = true;
            changed = true;
          }
        }
      }
      if (changed) {
        localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(next));
      }
      return changed ? next : prev;
    });
  }, [pathname, mounted]);

  const toggleCollapse = () => {
    const nextState = !collapsed;
    setCollapsed(nextState);
    localStorage.setItem("sidebar-collapsed", String(nextState));
  };

  const toggleExpanded = (href: string) => {
    setExpanded((prev) => {
      const next = { ...prev, [href]: !prev[href] };
      localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
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
              nxtQA
            </span>
            <span className="text-[10px] font-medium text-cyan-400 tracking-wider uppercase leading-none mt-0.5">
              AI Command Center for Quality
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
                if (item.children && item.children.length > 0) {
                  return (
                    <ParentItem
                      key={item.href}
                      item={item}
                      pathname={pathname}
                      projectId={projectId}
                      collapsed={collapsed}
                      expanded={Boolean(expanded[item.href])}
                      onToggle={() => toggleExpanded(item.href)}
                    />
                  );
                }
                return (
                  <LeafItem
                    key={item.href}
                    item={item}
                    pathname={pathname}
                    projectId={projectId}
                    collapsed={collapsed}
                  />
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

type LeafProps = {
  item: NavItem;
  pathname: string;
  projectId: string | null;
  collapsed: boolean;
  nested?: boolean;
};

function LeafItem({ item, pathname, projectId, collapsed, nested }: LeafProps) {
  const active = isActiveHref(pathname, item.href);
  const href = withProject(item.href, projectId);
  return (
    <Link
      href={href}
      title={collapsed ? item.label : undefined}
      className={cn(
        "flex items-center gap-3 rounded-lg text-xs font-medium transition-all duration-150",
        nested ? "pl-8 pr-3 py-1.5" : "px-3 py-2",
        active
          ? "bg-[#1b59f8] text-white shadow-sm"
          : "text-slate-400 hover:bg-[#13223f] hover:text-white"
      )}
    >
      <item.icon className={cn("h-4 w-4 shrink-0", active ? "text-white" : "text-slate-400")} />
      {!collapsed && <span className="truncate flex-1">{item.label}</span>}
      {!collapsed && active && <ChevronRight className="ml-auto h-3 w-3 opacity-60" />}
    </Link>
  );
}

type ParentProps = {
  item: NavItem;
  pathname: string;
  projectId: string | null;
  collapsed: boolean;
  expanded: boolean;
  onToggle: () => void;
};

function ParentItem({ item, pathname, projectId, collapsed, expanded, onToggle }: ParentProps) {
  const parentActive = isParentActive(pathname, item);
  const directHrefActive = isActiveHref(pathname, item.href);

  if (collapsed) {
    // In collapsed mode, render parent icon only — tapping it navigates to its default child
    const firstChild = item.children?.[0];
    const targetHref = withProject(firstChild?.href ?? item.href, projectId);
    return (
      <Link
        href={targetHref}
        title={item.label}
        className={cn(
          "flex items-center justify-center rounded-lg px-3 py-2 text-xs font-medium transition-all duration-150",
          parentActive
            ? "bg-[#1b59f8] text-white shadow-sm"
            : "text-slate-400 hover:bg-[#13223f] hover:text-white"
        )}
      >
        <item.icon className="h-4 w-4 shrink-0" />
      </Link>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`subnav-${item.href}`}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-all duration-150",
          directHrefActive
            ? "bg-[#1b59f8] text-white shadow-sm"
            : parentActive
            ? "bg-[#13223f] text-white"
            : "text-slate-400 hover:bg-[#13223f] hover:text-white"
        )}
      >
        <item.icon className={cn("h-4 w-4 shrink-0", parentActive ? "text-white" : "text-slate-400")} />
        <span className="truncate flex-1 text-left">{item.label}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-transform duration-200",
            expanded ? "rotate-0" : "-rotate-90",
            parentActive ? "text-white/70" : "text-slate-500"
          )}
        />
      </button>
      {expanded && (
        <div id={`subnav-${item.href}`} className="mt-1 space-y-0.5">
          {item.children!.map((child) => (
            <LeafItem
              key={child.href}
              item={child}
              pathname={pathname}
              projectId={projectId}
              collapsed={false}
              nested
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function Sidebar() {
  return (
    <Suspense fallback={<aside className="flex w-60 flex-col bg-[#091225] border-r border-[#13223f] text-slate-400" />}>
      <SidebarContent />
    </Suspense>
  );
}
