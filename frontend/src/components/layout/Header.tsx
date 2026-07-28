"use client";

import { useEffect, useState, useMemo, Suspense } from "react";
import { Bell, Plus, Search, User, CheckCircle2, AlertTriangle, MinusCircle, ChevronDown, HelpCircle, Sun, Moon, LogOut } from "lucide-react";
import Link from "next/link";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { authApi, projectsApi, usersApi, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

function HeaderContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [jiraSync, setJiraSync] = useState<{ synced: number; failures: number; conflicts: number } | null>(null);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<{ full_name: string; email: string; role: string } | null>(null);

  // Load current user profile
  useEffect(() => {
    usersApi.me()
      .then((res) => setCurrentUser(res.data))
      .catch((err) => console.error("Failed to load current user:", err));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setJiraSync(null);
      return;
    }
    projectsApi.dashboardMetrics(selectedProjectId)
      .then(({ data }) => setJiraSync({
        synced: data.jiraSync.syncedCount,
        failures: data.jiraSync.failureCount,
        conflicts: data.jiraSync.conflictCount,
      }))
      .catch(() => setJiraSync(null));
  }, [selectedProjectId]);

  const userInitials = useMemo(() => {
    if (!currentUser?.full_name) return "??";
    const parts = currentUser.full_name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + (parts[parts.length - 1] ? parts[parts.length - 1][0] : "")).toUpperCase();
  }, [currentUser]);

  const roleLabel = useMemo(() => {
    if (!currentUser?.role) return "";
    const map: Record<string, string> = {
      admin: "Platform Admin",
      qa_engineer: "QA Engineer",
      qa_lead: "QA Lead",
      viewer: "Viewer/Auditor",
    };
    return map[currentUser.role.toLowerCase()] ?? currentUser.role.replace(/_/g, " ");
  }, [currentUser]);

  // Load projects list
  useEffect(() => {
    projectsApi.list()
      .then((res) => {
        setProjects(res.data);
        const urlProject = Number(searchParams.get("project"));
        if (urlProject && res.data.some(p => p.id === urlProject)) {
          setSelectedProjectId(urlProject);
        } else if (res.data.length > 0) {
          setSelectedProjectId(res.data[0].id);
          updateQueryParam("project", String(res.data[0].id));
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync state if query parameter changes externally
  useEffect(() => {
    const urlProject = Number(searchParams.get("project"));
    if (urlProject && urlProject !== selectedProjectId) {
      setSelectedProjectId(urlProject);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const updateQueryParam = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set(key, value);
    router.push(`${pathname}?${params.toString()}`);
  };

  function signOut() {
    authApi.logout();
    router.push("/login");
  }

  // Get active page name from path
  const getPageTitle = () => {
    const segment = pathname.split("/").filter(Boolean)[0] || "dashboard";
    return segment.split("-").map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
  };

  return (
    <header className="flex h-14 items-center justify-between gap-3 border-b bg-white px-4 xl:px-6 shrink-0 z-10 select-none">
      {/* Left side: Breadcrumb & selectors */}
      <div className="flex min-w-0 items-center gap-3 xl:gap-6">
        {/* Breadcrumb path */}
        <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
          <Link href="/dashboard" className="hover:text-slate-800 transition-colors">
            e&amp; STLC
          </Link>
          <span className="text-slate-300">/</span>
          <span className="text-[#1b59f8] font-semibold">{getPageTitle()}</span>
        </div>

        {/* Project Selector Dropdown */}
        {projects.length > 0 && (
          <div className="hidden min-w-0 sm:flex items-center gap-2 border-l border-slate-100 pl-3 xl:pl-6">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Project
            </span>
            <select
              value={selectedProjectId ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedProjectId(Number(val));
                updateQueryParam("project", val);
              }}
              className="w-[220px] appearance-none truncate bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-800 rounded-lg text-xs font-medium px-3 py-1.5 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer select-none 2xl:w-[280px]"
              style={{
                backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                backgroundPosition: 'right 0.5rem center',
                backgroundSize: '1.25rem 1.25rem',
                backgroundRepeat: 'no-repeat',
              }}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Jira Sync Badge */}
        <div className={cn(
          "hidden shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-[10px] font-semibold xl:flex",
          jiraSync && (jiraSync.failures > 0 || jiraSync.conflicts > 0)
            ? "border-red-100 bg-red-50 text-red-700"
            : jiraSync && jiraSync.synced > 0
              ? "border-emerald-100 bg-emerald-50 text-emerald-700"
              : "border-slate-200 bg-slate-50 text-slate-500"
        )}>
          {jiraSync && (jiraSync.failures > 0 || jiraSync.conflicts > 0)
            ? <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            : jiraSync && jiraSync.synced > 0
              ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              : <MinusCircle className="h-3.5 w-3.5 shrink-0" />}
          <span>
            {jiraSync && (jiraSync.failures > 0 || jiraSync.conflicts > 0)
              ? `${jiraSync.failures + jiraSync.conflicts} Jira sync issue(s)`
              : jiraSync && jiraSync.synced > 0
                ? `${jiraSync.synced} Jira item(s) synced`
                : "No Jira sync activity"}
          </span>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex shrink-0 items-center gap-2 xl:gap-4">
        {/* Search */}
        <button className="rounded-lg p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-800 transition-colors">
          <Search className="h-4.5 w-4.5" />
        </button>

        {/* Notifications */}
        <button className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-800 transition-colors">
          <Bell className="h-4.5 w-4.5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white" />
        </button>

        {/* Help Center */}
        <button className="rounded-lg p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-800 transition-colors">
          <HelpCircle className="h-4.5 w-4.5" />
        </button>

        {/* Light/Dark toggle placeholder */}
        <button className="rounded-lg p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-800 transition-colors">
          <Moon className="h-4.5 w-4.5" />
        </button>

        {/* User Profile dropdown */}
        <div className="relative">
          <button 
            onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
            className="flex items-center gap-2.5 pl-3 border-l border-slate-100 text-left focus:outline-none"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-tr from-[#1b59f8] to-cyan-500 text-white font-semibold text-xs shadow-sm uppercase select-none">
              {userInitials}
            </div>
            <div className="hidden xl:flex flex-col">
              <span className="text-xs font-semibold text-slate-800 leading-none">{currentUser?.full_name ?? "Loading..."}</span>
              <span className="text-[10px] text-slate-500 mt-1 font-medium leading-none capitalize">{roleLabel || "..."}</span>
            </div>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400 hidden sm:block" />
          </button>

          {profileDropdownOpen && (
            <>
              <div 
                className="fixed inset-0 z-10" 
                onClick={() => setProfileDropdownOpen(false)}
              />
              <div className="absolute right-0 mt-2.5 w-48 rounded-xl border border-slate-200 bg-white py-1 shadow-lg z-20 transition-all duration-200">
                <div className="px-4 py-2 border-b border-slate-50">
                  <p className="text-xs font-semibold text-slate-800">{currentUser?.full_name ?? "..."}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{currentUser?.email ?? "..."}</p>
                </div>
                <button
                  onClick={() => {
                    setProfileDropdownOpen(false);
                    signOut();
                  }}
                  className="flex w-full items-center gap-2 px-4 py-2 text-left text-xs text-red-600 hover:bg-red-50 transition-colors"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function Header() {
  return (
    <Suspense fallback={<header className="flex h-14 items-center justify-between border-b bg-white px-6 shrink-0 w-full" />}>
      <HeaderContent />
    </Suspense>
  );
}
