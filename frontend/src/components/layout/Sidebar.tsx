"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  Boxes,
  Bug,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  Hand,
  Hexagon,
  Home,
  Layers,
  LayoutDashboard,
  MoreHorizontal,
  Play,
  Radar,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  TerminalSquare,
  TestTube2,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { navigationApi } from "@/lib/api";

type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  children?: NavItem[];
  trailingChevron?: boolean;
};

type NavGroup = {
  group: string;
  icon: LucideIcon;
  href?: string;
  items: NavItem[];
  defaultExpanded?: boolean;
  dividerBefore?: boolean;
  badge?: string;
};

const NAV_ITEMS: NavGroup[] = [
  {
    group: "Overview",
    icon: Home,
    defaultExpanded: true,
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
      { label: "Test Cases", href: "/test-cases", icon: TestTube2 },
    ],
  },
  {
    group: "AI Automation Lab",
    icon: FlaskConical,
    defaultExpanded: true,
    items: [
      { label: "Applications", href: "/applications", icon: Boxes, trailingChevron: true },
      { label: "AI Automation Studio", href: "/automation", icon: Sparkles, trailingChevron: true },
      { label: "Playwright AI Studio", href: "/playwright-studio", icon: Bot },
    ],
  },
  {
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
    // Separate module. Visible only to the Test_Automation_Users global role
    // and to platform admins — the server decides via /users/me/navigation and
    // this list is filtered against its answer, so the group never renders for
    // a role whose requests the backend would 404 anyway.
    group: "Test Automation Studio",
    icon: TerminalSquare,
    defaultExpanded: true,
    dividerBefore: true,
    items: [
      {
        label: "Requirement Coverage Assessment",
        href: "/test-automation-studio?view=coverage",
        icon: FileText,
      },
      {
        label: "Automation TC Coverage",
        href: "/test-automation-studio?view=test-cases",
        icon: TestTube2,
      },
      {
        label: "Automation Script Lab",
        href: "/test-automation-studio?view=script-lab",
        icon: Cpu,
      },
    ],
  },
  {
    group: "Operations",
    icon: Activity,
    dividerBefore: true,
    items: [
      { label: "AI Agents", href: "/agents", icon: Bot },
      { label: "Agent Run Logs", href: "/agents/logs", icon: BookOpen },
      { label: "Resource Intelligence", href: "/resource-intelligence", icon: Users },
    ],
  },
  {
    group: "RAG & Knowledge Base",
    icon: Database,
    href: "/knowledge-base",
    badge: "Beta",
    items: [],
  },
  {
    group: "Settings",
    icon: SlidersHorizontal,
    defaultExpanded: true,
    dividerBefore: true,
    items: [
      { label: "Project Settings", href: "/settings", icon: Settings },
      { label: "Users & Roles", href: "/users", icon: Users },
      { label: "Taxonomy", href: "/taxonomy", icon: Layers },
    ],
  },
  {
    group: "Others",
    icon: MoreHorizontal,
    dividerBefore: true,
    items: [
      { label: "Test Data", href: "/test-data", icon: Database },
      { label: "Grounded Automation (PoC)", href: "/grounded-automation", icon: Target },
    ],
  },
];

// Which groups render before the server has answered. Everything except the
// Test Automation Studio: showing the studio optimistically would flash a
// module at users who may not have it, and hiding the rest would blank the
// sidebar for the majority on every page load.
const DEFAULT_VISIBLE_GROUPS = NAV_ITEMS.map((group) => group.group).filter(
  (group) => group !== "Test Automation Studio",
);

const EXPANDED_STORAGE_KEY = "sidebar-expanded-items";
// Versioned so the new compact information architecture gets its intended
// defaults instead of inheriting the previous menu's "everything open" state.
const EXPANDED_GROUPS_STORAGE_KEY = "sidebar-expanded-groups-v2";
const DEFAULT_EXPANDED_GROUPS = Object.fromEntries(
  NAV_ITEMS.filter((group) => group.defaultExpanded).map((group) => [group.group, true]),
) as Record<string, boolean>;

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
  if (path === "/agents") return pathname === "/agents";
  const pathActive = pathname === path || pathname.startsWith(`${path}/`);
  if (!pathActive) return false;
  const expectedView = params.get("view");
  return expectedView ? new URLSearchParams(currentQuery).get("view") === expectedView : true;
}

function isParentActive(pathname: string, currentQuery: string, item: NavItem): boolean {
  if (isActiveHref(pathname, currentQuery, item.href)) return true;
  return Boolean(item.children?.some((child) => isActiveHref(pathname, currentQuery, child.href)));
}

function isGroupActive(pathname: string, currentQuery: string, group: NavGroup): boolean {
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
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(DEFAULT_EXPANDED_GROUPS);
  const [visibleGroups, setVisibleGroups] = useState<string[]>(DEFAULT_VISIBLE_GROUPS);

  useEffect(() => {
    let active = true;
    navigationApi
      .get()
      .then((response) => {
        if (active && Array.isArray(response.data?.nav_groups)) {
          setVisibleGroups(response.data.nav_groups);
        }
      })
      .catch(() => {
        // An unreachable or older backend leaves the default in place: today's
        // menu, without the new module. Failing closed on the studio and open
        // on everything else keeps the sidebar usable during an outage.
      });
    return () => {
      active = false;
    };
  }, []);

  const navItems = useMemo(
    () => NAV_ITEMS.filter((group) => visibleGroups.includes(group.group)),
    [visibleGroups],
  );

  useEffect(() => {
    setMounted(true);
    const savedCollapsed = localStorage.getItem("sidebar-collapsed");
    if (savedCollapsed) setCollapsed(savedCollapsed === "true");

    const savedExpanded = localStorage.getItem(EXPANDED_STORAGE_KEY);
    if (savedExpanded) {
      try {
        setExpanded(JSON.parse(savedExpanded));
      } catch {
        // Ignore malformed legacy preferences.
      }
    }

    const savedGroups = localStorage.getItem(EXPANDED_GROUPS_STORAGE_KEY);
    if (savedGroups) {
      try {
        setExpandedGroups({ ...DEFAULT_EXPANDED_GROUPS, ...JSON.parse(savedGroups) });
      } catch {
        // Ignore malformed legacy preferences.
      }
    }
  }, []);

  useEffect(() => {
    if (!mounted) return;
    setExpanded((previous) => {
      const next = { ...previous };
      let changed = false;
      for (const group of navItems) {
        for (const item of group.items) {
          if (item.children && isParentActive(pathname, currentQuery, item) && !next[item.href]) {
            next[item.href] = true;
            changed = true;
          }
        }
      }
      if (changed) localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(next));
      return changed ? next : previous;
    });
  }, [pathname, currentQuery, mounted, navItems]);

  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar-collapsed", String(next));
  };

  const toggleExpanded = (href: string) => {
    setExpanded((previous) => {
      const next = { ...previous, [href]: !previous[href] };
      localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const isGroupExpanded = (groupName: string) =>
    expandedGroups[groupName] ?? DEFAULT_EXPANDED_GROUPS[groupName] ?? false;

  const toggleGroup = (groupName: string) => {
    setExpandedGroups((previous) => {
      const next = { ...previous, [groupName]: !isGroupExpanded(groupName) };
      localStorage.setItem(EXPANDED_GROUPS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  if (!mounted) return <SidebarShell collapsed={false} />;

  return (
    <aside
      className={cn(
        "relative flex h-full shrink-0 select-none flex-col overflow-hidden border-r border-[#8b2529]/70 text-white transition-[width] duration-300 ease-out",
        collapsed ? "w-[5.25rem]" : "w-[19rem]",
      )}
      style={{
        backgroundColor: "#170405",
        backgroundImage:
          "radial-gradient(circle at 15% 8%, rgba(183,25,32,0.32), transparent 27%), radial-gradient(circle at 88% 42%, rgba(122,11,13,0.16), transparent 34%), linear-gradient(180deg, #2a0709 0%, #170405 54%, #120304 100%)",
        boxShadow: "8px 0 28px -22px rgba(77,5,7,0.9), inset -1px 0 rgba(255,255,255,0.025)",
      }}
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[linear-gradient(115deg,transparent_0%,rgba(255,255,255,0.018)_36%,transparent_64%)]" />

      <div className={cn("relative z-10 shrink-0 border-b border-white/10", collapsed ? "px-3 py-5" : "px-5 py-5")}>
        <div className={cn("flex items-center", collapsed ? "justify-center" : "gap-4")}>
          <div className="relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-[18px] border border-[#d52b31]/45 bg-gradient-to-br from-[#a4181d] via-[#731014] to-[#3f090b] shadow-[0_14px_32px_-18px_rgba(213,43,49,0.95)]">
            <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(circle_at_32%_24%,rgba(255,255,255,0.18),transparent_42%)]" />
            <Hexagon className="relative h-10 w-10 stroke-[2.6] text-white" />
            <Bot className="absolute h-[18px] w-[18px] text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-[28px] font-black leading-none tracking-[0.08em] text-white drop-shadow-sm">QAI</p>
              <p className="mt-2 whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.14em] text-white/64">
                Quality Assurance Intelligence
              </p>
            </div>
          )}
        </div>
      </div>

      <nav aria-label="Primary navigation" className="relative z-10 min-h-0 flex-1 overflow-y-auto px-3 py-4 no-scrollbar">
        <div className="space-y-1">
          {navItems.map((group) => {
            const groupActive = isGroupActive(pathname, currentQuery, group);
            const groupExpanded = isGroupExpanded(group.group);
            const groupId = `navgroup-${group.group.replace(/\s+/g, "-").toLowerCase()}`;

            return (
              <div
                key={group.group}
                className={cn(group.dividerBefore && "mt-3 border-t border-white/10 pt-3")}
              >
                {group.href ? (
                  <Link
                    href={withProject(group.href, projectId)}
                    title={collapsed ? group.group : undefined}
                    className={cn(
                      "group relative flex min-h-11 w-full items-center rounded-xl border border-transparent transition-all duration-200",
                      collapsed ? "justify-center px-2" : "gap-3 px-3",
                      groupActive
                        ? "border-[#d52b31]/55 bg-gradient-to-r from-[#9e171c]/90 to-[#6e1014]/78 text-white shadow-[0_12px_28px_-20px_rgba(213,43,49,0.95)]"
                        : "text-white/82 hover:border-white/10 hover:bg-white/[0.055] hover:text-white",
                    )}
                  >
                    {groupActive && <span aria-hidden="true" className="absolute -left-3 h-8 w-1 rounded-r-full bg-[#f0444a] shadow-[0_0_14px_rgba(240,68,74,0.8)]" />}
                    <NavIcon icon={group.icon} active={groupActive} prominent />
                    {!collapsed && (
                      <>
                        <span className="min-w-0 flex-1 truncate text-left text-[13px] font-semibold">{group.group}</span>
                        {group.badge && (
                          <span className="rounded-lg border border-[#d52b31]/20 bg-[#7a1115]/55 px-2 py-1 text-[10px] font-bold text-[#ff686d]">
                            {group.badge}
                          </span>
                        )}
                      </>
                    )}
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      if (collapsed) setCollapsed(false);
                      else toggleGroup(group.group);
                    }}
                    aria-expanded={!collapsed && groupExpanded}
                    aria-controls={groupId}
                    title={collapsed ? group.group : undefined}
                    className={cn(
                      "group relative flex min-h-11 w-full items-center rounded-xl border border-transparent transition-all duration-200",
                      collapsed ? "justify-center px-2" : "gap-3 px-3",
                      groupActive
                        ? "border-[#d52b31]/55 bg-gradient-to-r from-[#a3181d]/95 to-[#741014]/82 text-white shadow-[0_14px_30px_-20px_rgba(213,43,49,0.95)]"
                        : "text-white/82 hover:border-white/10 hover:bg-white/[0.055] hover:text-white",
                    )}
                  >
                    {groupActive && <span aria-hidden="true" className="absolute -left-3 h-8 w-1 rounded-r-full bg-[#f0444a] shadow-[0_0_14px_rgba(240,68,74,0.85)]" />}
                    <NavIcon icon={group.icon} active={groupActive} prominent />
                    {!collapsed && (
                      <>
                        <span className="min-w-0 flex-1 truncate text-left text-[13px] font-semibold">{group.group}</span>
                        <ChevronDown
                          className={cn(
                            "h-4 w-4 shrink-0 text-white/58 transition-transform duration-200",
                            groupExpanded ? "rotate-0" : "-rotate-90",
                          )}
                        />
                      </>
                    )}
                  </button>
                )}

                {!group.href && !collapsed && (
                  <div id={groupId} className={cn("overflow-hidden", !groupExpanded && "hidden")}>
                    <div className="space-y-0.5 pb-1 pt-1">
                      {group.items.map((item) =>
                        item.children?.length ? (
                          <ParentItem
                            key={item.href}
                            item={item}
                            pathname={pathname}
                            currentQuery={currentQuery}
                            projectId={projectId}
                            expanded={Boolean(expanded[item.href])}
                            onToggle={() => toggleExpanded(item.href)}
                          />
                        ) : (
                          <LeafItem
                            key={item.href}
                            item={item}
                            pathname={pathname}
                            currentQuery={currentQuery}
                            projectId={projectId}
                          />
                        ),
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </nav>

      <div className={cn("relative z-10 shrink-0 border-t border-white/10", collapsed ? "p-3" : "p-4")}>
        {collapsed ? (
          <button
            type="button"
            onClick={toggleCollapse}
            className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-white/70 transition hover:border-[#d52b31]/45 hover:bg-[#7a1014]/55 hover:text-white"
            aria-label="Expand sidebar"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        ) : (
          <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035] p-3.5 shadow-[inset_0_1px_rgba(255,255,255,0.025)]">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 right-0 w-24 opacity-20"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(135deg, transparent 0 10px, rgba(213,43,49,0.45) 10px 11px)",
                maskImage: "linear-gradient(to left, black, transparent)",
              }}
            />
            <div className="relative flex items-center gap-3">
              <ShieldCheck className="h-6 w-6 shrink-0 text-white/66" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-semibold text-white/92">Secure. Governed. Intelligent.</p>
                <p className="mt-0.5 truncate text-[9px] font-medium text-white/48">Delivering Quality with Intelligence</p>
              </div>
              <button
                type="button"
                onClick={toggleCollapse}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-black/10 text-white/55 transition hover:border-[#d52b31]/45 hover:bg-[#7a1014]/55 hover:text-white"
                aria-label="Collapse sidebar"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

function NavIcon({ icon: Icon, active, prominent = false }: { icon: LucideIcon; active: boolean; prominent?: boolean }) {
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center transition-all duration-200",
        prominent ? "h-8 w-8 rounded-lg border" : "h-7 w-7",
        prominent && active
          ? "border-white/10 bg-[#c32127]/72 text-white shadow-[0_8px_18px_-12px_rgba(255,75,82,0.95)]"
          : prominent
            ? "border-transparent text-white/76 group-hover:text-white"
            : active
              ? "text-[#ff565c]"
              : "text-white/68 group-hover:text-white/90",
      )}
    >
      <Icon className={cn(prominent ? "h-[19px] w-[19px]" : "h-[18px] w-[18px]", "stroke-[1.85]")} />
    </span>
  );
}

function LeafItem({
  item,
  pathname,
  currentQuery,
  projectId,
  nested,
}: {
  item: NavItem;
  pathname: string;
  currentQuery: string;
  projectId: string | null;
  nested?: boolean;
}) {
  const active = isActiveHref(pathname, currentQuery, item.href);
  return (
    <Link
      href={withProject(item.href, projectId)}
      className={cn(
        "group flex min-h-10 items-center rounded-xl border border-transparent text-[12px] font-medium transition-all duration-200",
        nested ? "ml-7 gap-2.5 py-1.5 pl-4 pr-3" : "gap-3 py-1.5 pl-3 pr-3",
        active
          ? "border-white/[0.07] bg-white/[0.07] text-white shadow-[inset_3px_0_0_rgba(213,43,49,0.8)]"
          : "text-white/66 hover:border-white/[0.06] hover:bg-white/[0.045] hover:text-white",
      )}
    >
      <NavIcon icon={item.icon} active={active} />
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
      {(item.trailingChevron || active) && <ChevronRight className={cn("h-3.5 w-3.5 shrink-0", active ? "text-[#ff6268]" : "text-white/42")} />}
    </Link>
  );
}

function ParentItem({
  item,
  pathname,
  currentQuery,
  projectId,
  expanded,
  onToggle,
}: {
  item: NavItem;
  pathname: string;
  currentQuery: string;
  projectId: string | null;
  expanded: boolean;
  onToggle: () => void;
}) {
  const parentActive = isParentActive(pathname, currentQuery, item);
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`subnav-${item.href}`}
        className={cn(
          "group flex min-h-10 w-full items-center gap-3 rounded-xl border border-transparent py-1.5 pl-3 pr-3 text-[12px] font-medium transition-all duration-200",
          parentActive
            ? "border-white/[0.07] bg-white/[0.07] text-white"
            : "text-white/66 hover:border-white/[0.06] hover:bg-white/[0.045] hover:text-white",
        )}
      >
        <NavIcon icon={item.icon} active={parentActive} />
        <span className="min-w-0 flex-1 truncate text-left">{item.label}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 text-white/42 transition-transform", expanded ? "rotate-0" : "-rotate-90")} />
      </button>
      {expanded && (
        <div id={`subnav-${item.href}`} className="space-y-0.5">
          {item.children!.map((child) => (
            <LeafItem
              key={child.href}
              item={child}
              pathname={pathname}
              currentQuery={currentQuery}
              projectId={projectId}
              nested
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SidebarShell({ collapsed }: { collapsed: boolean }) {
  return (
    <aside
      className={cn("h-full shrink-0 border-r border-[#8b2529]/70 bg-[#170405]", collapsed ? "w-[5.25rem]" : "w-[19rem]")}
    />
  );
}

export function Sidebar() {
  return (
    <Suspense fallback={<SidebarShell collapsed={false} />}>
      <SidebarContent />
    </Suspense>
  );
}
