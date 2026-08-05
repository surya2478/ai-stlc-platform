"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import {
  LayoutDashboard, FileText, ClipboardList,
  TestTube2, Play, Bug, BarChart3, Settings,
  Bot, ChevronRight, ChevronDown, Users, Database,
  ChevronLeft, BookOpen,
  Hand, Cpu, Sparkles, Gauge, Target,
  Radar,
  Boxes,
  Layers,
  FlaskConical,
  MoreHorizontal,
  Home,
  Workflow,
  Compass,
  Activity,
  SlidersHorizontal,
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
  // Group headers render as nav rows (same treatment as a parent item like
  // Test Planning), so each one carries its own icon.
  icon: LucideIcon;
  // A section that is one destination rather than a list of them. The header
  // becomes the link and there is nothing to expand — used where the screens
  // in the section are tabs on a single page (Applications), so the sidebar
  // does not repeat what the tab bar already shows.
  href?: string;
  items: NavItem[];
};

const NAV_ITEMS: NavGroup[] = [
  {
    group: "Overview",
    icon: Home,
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Command Centre", href: "/autonomous-lab/missions", icon: Radar },
    ],
  },
  {
    group: "AI Planning & Test Lab",
    icon: Workflow,
    items: [
      { label: "Requirements", href: "/requirements", icon: FileText },
      { label: "Test Planning & Scenarios", href: "/test-planning", icon: ClipboardList },
      // One entry, not four. Test Editor, Test Case Approval and Journey Graph
      // are tabs on this same page (see TestCasesTabs) — same treatment as
      // Requirements and Applications.
      { label: "Test Cases", href: "/test-cases", icon: TestTube2 },
    ],
  },
  // "Automation Studio Core" (Automation Workspace, Live Recorder, Automation
  // Assets) is deliberately not in the tree. It was a second, parallel
  // automation product sitting beside the one people actually use: the same
  // approved test case could be worked either through a suite/member/asset
  // hierarchy or through AI Automation Studio, and nothing reconciled the two.
  //
  // The single automation destination is "AI Automation Studio" (/automation),
  // fed by Applications → Live Discovery Session → Application Model. The
  // `?view=workspace|recorder|ir|script|validation` routes still resolve, so
  // existing deep links and in-page navigation keep working — they are just no
  // longer advertised as places to start.
  {
    // The three screens an automation flow actually moves through, in order:
    // ground the app (Applications), script it (AI Automation Studio), or drive
    // it directly through the MCP runner (Playwright AI Studio).
    //
    // A section rather than a parent item: it heads a body of work the same way
    // "AI Planning & Test Lab" does, and only the section header carries that
    // weight. As a nested item it rendered a rank below what it names.
    group: "AI Automation Lab",
    icon: FlaskConical,
    items: [
      // Discovery, Model and API & Network are tabs on this page (see
      // ApplicationsTabs), the same way Analysis and Traceability are tabs
      // under a single "Requirements" entry — one entry, not four.
      { label: "Applications", href: "/applications", icon: Compass },
      { label: "AI Automation Studio", href: "/automation", icon: Sparkles },
      { label: "Playwright AI Studio", href: "/playwright-studio", icon: Bot },
    ],
  },
  {
    // Everything that happens to a test case after it is scripted: running it,
    // then the two artifacts a run produces. Defects and Reports used to sit as
    // siblings of Execution, which read as if they were separate phases rather
    // than its outputs.
    group: "AI Execution Lab",
    icon: Play,
    items: [
      { label: "Manual Execution", href: "/execution/manual", icon: Hand },
      { label: "Automation Execution", href: "/execution/automation", icon: Cpu },
      { label: "Execution Dashboard", href: "/execution/dashboard", icon: Gauge },
      { label: "Defects", href: "/defects", icon: Bug },
      { label: "Reports", href: "/reports", icon: BarChart3 },
    ],
  },
  {
    group: "Operations",
    icon: Activity,
    items: [
      { label: "AI Agents", href: "/agents", icon: Bot },
      { label: "Agent Run Logs", href: "/agents/logs", icon: BookOpen },
      { label: "Resource Intelligence", href: "/resource-intelligence", icon: Users },
    ],
  },
  {
    group: "Settings",
    icon: SlidersHorizontal,
    items: [
      { label: "Project Settings", href: "/settings", icon: Settings },
      { label: "Users & Roles", href: "/users", icon: Users },
      // Organization-wide master data, not project-scoped — it sits beside
      // Users & Roles rather than inside Project Settings for that reason.
      { label: "Taxonomy", href: "/taxonomy", icon: Layers },
    ],
  },
  {
    // Last in the tree by design: a catch-all for capabilities outside the
    // ordered Planning → Automation → Execution flow above.
    group: "Others",
    icon: MoreHorizontal,
    items: [
      { label: "Test Data", href: "/test-data", icon: Database },
      { label: "Grounded Automation (PoC)", href: "/grounded-automation", icon: Target },
    ],
  },
];

const EXPANDED_STORAGE_KEY = "sidebar-expanded-items";
const EXPANDED_GROUPS_STORAGE_KEY = "sidebar-expanded-groups";

function withProject(href: string, projectId: string | null): string {
  if (!projectId) return href;
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}project=${projectId}`;
}

function parseHref(href: string) {
  const [path, query = ""] = href.split("?");
  return { path, params: new URLSearchParams(query) };
}

function isActiveHref(pathname: string, currentQuery: string, href: string): boolean {
  const { path, params } = parseHref(href);
  if (path === "/agents") {
    return pathname === "/agents";
  }
  const pathActive = pathname === path || pathname.startsWith(path + "/");
  if (!pathActive) return false;
  const currentParams = new URLSearchParams(currentQuery);
  const expectedView = params.get("view");
  if (expectedView) {
    const currentView = currentParams.get("view");
    return currentView === expectedView;
  }
  // "/automation" and "/applications" are each a single nav entry over several
  // `?view=` screens, so the entry stays lit across all of them — exactly as
  // "Requirements" stays lit on its own tabs. "/automation" used to be excluded
  // here because Automation Workspace, Live Recorder and Automation Assets were
  // sibling nav items that had to win the highlight; those entries are gone, so
  // the exclusion now only served to make the sidebar go dark on a view of the
  // very screen you are looking at.
  return true;
}

function isParentActive(pathname: string, currentQuery: string, item: NavItem): boolean {
  if (isActiveHref(pathname, currentQuery, item.href)) return true;
  return Boolean(item.children?.some((c) => isActiveHref(pathname, currentQuery, c.href)));
}

function isGroupActive(pathname: string, currentQuery: string, group: NavGroup): boolean {
  // A single-destination section has no items to derive activity from — its own
  // href is the only thing to match.
  if (group.href) return isActiveHref(pathname, currentQuery, group.href);
  return group.items.some((item) => isParentActive(pathname, currentQuery, item));
}

function SidebarContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");
  const currentQuery = searchParams.toString();

  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  // Groups are open unless explicitly collapsed, so a first visit still shows
  // the whole menu. Only an entry of `false` hides one.
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

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
    const savedGroups = localStorage.getItem(EXPANDED_GROUPS_STORAGE_KEY);
    if (savedGroups) {
      try {
        setExpandedGroups(JSON.parse(savedGroups));
      } catch {
        /* ignore */
      }
    }
  }, []);

  useEffect(() => {
    if (!mounted) return;
    // Reopen the group holding the current route, so navigating can never
    // leave the active item hidden inside a collapsed group. This runs on route
    // change only, so collapsing the group you are already in stays collapsed.
    setExpandedGroups((prev) => {
      const active = NAV_ITEMS.find((group) => isGroupActive(pathname, currentQuery, group));
      if (!active || prev[active.group] !== false) return prev;
      const next = { ...prev, [active.group]: true };
      localStorage.setItem(EXPANDED_GROUPS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, [pathname, currentQuery, mounted]);

  useEffect(() => {
    if (!mounted) return;
    // Auto-expand any parent whose child matches the current route
    setExpanded((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const group of NAV_ITEMS) {
        for (const item of group.items) {
          if (item.children && isParentActive(pathname, currentQuery, item) && !next[item.href]) {
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
  }, [pathname, currentQuery, mounted]);

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

  const isGroupExpanded = (groupName: string) => expandedGroups[groupName] !== false;

  const toggleGroup = (groupName: string) => {
    setExpandedGroups((prev) => {
      const next = { ...prev, [groupName]: prev[groupName] === false };
      localStorage.setItem(EXPANDED_GROUPS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  if (!mounted) {
    return <aside className="flex w-60 flex-col bg-sidebar border-r border-app-sidebar-border text-app-sidebar-muted" />;
  }

  return (
    <aside
      className={cn(
        "flex flex-col border-r border-app-sidebar-border bg-sidebar text-app-sidebar-muted transition-all duration-300 ease-in-out select-none",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 border-b border-app-sidebar-border px-4 overflow-hidden shrink-0">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-app-brand-500 to-app-brand-700 shadow-md">
          <Bot className="h-4.5 w-4.5 text-white" />
        </div>
        {!collapsed && (
          <div className="flex flex-col min-w-0 transition-opacity duration-300">
            <span className="font-bold text-sm text-white leading-tight tracking-wide truncate">
              QAI
            </span>
            <span className="text-[10px] font-medium text-app-sidebar-muted tracking-wider uppercase leading-none mt-0.5">
              QAI Command Center
            </span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 space-y-4 no-scrollbar">
        {NAV_ITEMS.map((group) => {
          const groupActive = isGroupActive(pathname, currentQuery, group);
          // When the rail is collapsed there is no header to click, so items
          // always show — otherwise a group could become unreachable.
          const showItems = collapsed || isGroupExpanded(group.group);
          const groupId = `navgroup-${group.group.replace(/\s+/g, "-").toLowerCase()}`;

          return (
            <div key={group.group} className="px-2">
              {group.href ? (
                // A single-destination section: the header navigates instead of
                // expanding. Rendered in both rail states — when collapsed the
                // icon alone is the link, since there are no items beneath it to
                // fall back to.
                <Link
                  href={withProject(group.href, projectId)}
                  title={collapsed ? group.group : undefined}
                  className={cn(
                    "mb-1.5 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-150",
                    collapsed && "justify-center px-0",
                    groupActive
                      ? "bg-[#B71920] text-white"
                      : "text-app-sidebar-muted hover:bg-app-sidebar-hover hover:text-white",
                  )}
                >
                  <group.icon
                    className={cn("h-4 w-4 shrink-0", groupActive ? "text-white" : "text-app-sidebar-muted")}
                  />
                  {!collapsed && <span className="flex-1 truncate text-left">{group.group}</span>}
                </Link>
              ) : !collapsed ? (
                <button
                  type="button"
                  onClick={() => toggleGroup(group.group)}
                  aria-expanded={isGroupExpanded(group.group)}
                  aria-controls={groupId}
                  // Same row treatment as a parent item such as Test Planning:
                  // icon, normal-case label, full padding and hover — so a
                  // section header reads as prominently as the items under it.
                  className={cn(
                    "mb-1.5 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-150",
                    groupActive
                      ? "bg-app-sidebar-active text-white"
                      : "text-app-sidebar-muted hover:bg-app-sidebar-hover hover:text-white"
                  )}
                >
                  <group.icon
                    className={cn(
                      "h-4 w-4 shrink-0",
                      groupActive ? "text-white" : "text-app-sidebar-muted"
                    )}
                  />
                  <span className="truncate flex-1 text-left">{group.group}</span>
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 shrink-0 transition-transform duration-200",
                      isGroupExpanded(group.group) ? "rotate-0" : "-rotate-90",
                      groupActive ? "text-white/70" : "text-white/50"
                    )}
                  />
                </button>
              ) : (
                <div className="border-t border-app-sidebar-border my-3 first:hidden" />
              )}
              <div id={groupId} className={cn("space-y-0.5", !showItems && "hidden")}>
                {group.items.map((item) => {
                if (item.children && item.children.length > 0) {
                  return (
                    <ParentItem
                      key={item.href}
                      item={item}
                      pathname={pathname}
                      currentQuery={currentQuery}
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
                    currentQuery={currentQuery}
                    projectId={projectId}
                    collapsed={collapsed}
                  />
                );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      {/* Footer / Collapse Button */}
      <div className="border-t border-app-sidebar-border p-3 flex items-center justify-between shrink-0">
        {!collapsed && (
          <p className="text-[10px] text-white/50 font-mono pl-1">v1.0.0 — Enterprise</p>
        )}
        <button
          onClick={toggleCollapse}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-app-sidebar-border hover:bg-app-sidebar-hover hover:text-white transition-colors ml-auto"
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
  currentQuery: string;
  projectId: string | null;
  collapsed: boolean;
  nested?: boolean;
};

function LeafItem({ item, pathname, currentQuery, projectId, collapsed, nested }: LeafProps) {
  const active = isActiveHref(pathname, currentQuery, item.href);
  const href = withProject(item.href, projectId);
  return (
    <Link
      href={href}
      title={collapsed ? item.label : undefined}
      className={cn(
        "flex items-center gap-3 rounded-lg text-xs font-medium transition-all duration-150",
        nested ? "pl-8 pr-3 py-1.5" : "px-3 py-2",
        active
          ? "bg-[#B71920] text-white shadow-sm"
          : "text-app-sidebar-muted hover:bg-app-sidebar-hover hover:text-white"
      )}
    >
      <item.icon className={cn("h-4 w-4 shrink-0", active ? "text-white" : "text-app-sidebar-muted")} />
      {!collapsed && <span className="truncate flex-1">{item.label}</span>}
      {!collapsed && active && <ChevronRight className="ml-auto h-3 w-3 opacity-60" />}
    </Link>
  );
}

type ParentProps = {
  item: NavItem;
  pathname: string;
  currentQuery: string;
  projectId: string | null;
  collapsed: boolean;
  expanded: boolean;
  onToggle: () => void;
};

function ParentItem({ item, pathname, currentQuery, projectId, collapsed, expanded, onToggle }: ParentProps) {
  const parentActive = isParentActive(pathname, currentQuery, item);
  const directHrefActive = isActiveHref(pathname, currentQuery, item.href);

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
            ? "bg-[#B71920] text-white shadow-sm"
            : "text-app-sidebar-muted hover:bg-app-sidebar-hover hover:text-white"
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
            ? "bg-[#B71920] text-white shadow-sm"
            : parentActive
            ? "bg-app-sidebar-active text-white"
            : "text-app-sidebar-muted hover:bg-app-sidebar-hover hover:text-white"
        )}
      >
        <item.icon className={cn("h-4 w-4 shrink-0", parentActive ? "text-white" : "text-app-sidebar-muted")} />
        <span className="truncate flex-1 text-left">{item.label}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-transform duration-200",
            expanded ? "rotate-0" : "-rotate-90",
            parentActive ? "text-white/70" : "text-white/50"
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
              currentQuery={currentQuery}
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
    <Suspense fallback={<aside className="flex w-60 flex-col bg-sidebar border-r border-app-sidebar-border text-app-sidebar-muted" />}>
      <SidebarContent />
    </Suspense>
  );
}
