"use client";

import { FormEvent, useEffect, useMemo, useState, useCallback, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  Loader2,
  RefreshCw,
  Search,
  Shield,
  UserPlus,
  Users,
  XCircle,
} from "lucide-react";
import {
  getAuthProfile,
  projectsApi,
  usersApi,
  type Project,
  type ProjectMembership,
  type ProjectRole,
  type UserAccount,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const GLOBAL_ROLES = [
  { value: "admin", label: "Platform Admin" },
  { value: "qa_engineer", label: "QA Engineer" },
  { value: "qa_lead", label: "QA Lead" },
  { value: "viewer", label: "Viewer/Auditor" },
  // Sees only the Test Automation Studio, Operations, Settings and Others
  // navigation groups. Assign the matching project role of the same name too,
  // or the user reaches the studio with no permission to act in it.
  { value: "Test_Automation_Users", label: "Test Automation User" },
];

const PASSWORD_HINT = "Use 8-72 characters. Bcrypt rejects passwords longer than 72 bytes.";

function messageFromError(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join("; ");
  return typeof detail === "string" ? detail : fallback;
}

function getStatusVariant(ok: boolean): "success" | "secondary" {
  return ok ? "success" : "secondary";
}

// ── Main Content Component ───────────────────────────────────────────────────

function UserManagementContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [authProfile, setAuthProfile] = useState<any>(null);

  useEffect(() => {
    usersApi.me()
      .then((response) => {
        setAuthProfile({
          global_role: response.data.role,
        });
      })
      .catch(() => {
        setAuthProfile(getAuthProfile());
      });
  }, []);

  const selectedProjectId = Number(searchParams.get("project")) || null;
  const isPlatformAdmin = useMemo(() => {
    const role = authProfile?.global_role?.toLowerCase();
    return role === "admin" || role === "platform_admin";
  }, [authProfile]);

  const [users, setUsers] = useState<UserAccount[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [roles, setRoles] = useState<ProjectRole[]>([]);
  const [memberships, setMemberships] = useState<ProjectMembership[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [selectedProjectRole, setSelectedProjectRole] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    password: "",
    confirm_password: "",
    role: "qa_engineer",
    is_superuser: false,
  });

  const activeUsers = useMemo(() => users.filter((user) => user.is_active).length, [users]);
  const adminUsers = useMemo(() => users.filter((user) => user.is_active && (user.is_superuser || user.role === "admin")).length, [users]);
  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedProjectId), [projects, selectedProjectId]);

  const membershipRows = useMemo(
    () =>
      memberships.map((membership) => ({
        ...membership,
        user: users.find((user) => user.id === membership.user_id),
      })),
    [memberships, users]
  );

  const loadMemberships = useCallback(async (projectId: number) => {
    setError("");
    try {
      const response = await projectsApi.memberships(projectId);
      setMemberships(response.data);
    } catch (membershipError: any) {
      setMemberships([]);
      setError(messageFromError(membershipError, "You do not have permission to manage memberships for this project."));
    }
  }, []);

  const loadInitialData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [projectsResponse, rolesResponse] = await Promise.all([
        projectsApi.list(),
        projectsApi.roles(),
      ]);
      setProjects(projectsResponse.data);
      setRoles(rolesResponse.data);

      const activeProjId = selectedProjectId ?? projectsResponse.data[0]?.id ?? null;
      if (activeProjId && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(activeProjId));
        router.push(`${pathname}?${params.toString()}`);
      }

      if (activeProjId) {
        await loadMemberships(activeProjId);
      }

      if (rolesResponse.data.length > 0) {
        setSelectedProjectRole(rolesResponse.data[0].role);
      }
    } catch (loadError: any) {
      setError(messageFromError(loadError, "Could not load project data."));
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, searchParams, pathname, router, loadMemberships]);

  const loadUsersList = useCallback(async () => {
    if (!isPlatformAdmin && !selectedProjectId) {
      setUsers([]);
      return;
    }
    try {
      const usersResponse = await usersApi.list({
        limit: 200,
        search: search || undefined,
        project_id: selectedProjectId ?? undefined,
      });
      setUsers(usersResponse.data);
    } catch (loadError: any) {
      setError(messageFromError(loadError, "Could not load user list."));
    }
  }, [isPlatformAdmin, search, selectedProjectId]);

  // Initial load
  useEffect(() => {
    loadInitialData();
  }, []);

  // Sync users list with search input
  useEffect(() => {
    loadUsersList();
  }, [loadUsersList]);

  // Reload memberships when project ID changes
  useEffect(() => {
    if (selectedProjectId) {
      loadMemberships(selectedProjectId);
    } else {
      setMemberships([]);
    }
  }, [selectedProjectId, loadMemberships]);

  const handleRefresh = async () => {
    setLoading(true);
    await Promise.all([loadUsersList(), selectedProjectId ? loadMemberships(selectedProjectId) : Promise.resolve()]);
    setLoading(false);
  };

  function validateCreateForm() {
    if (!form.email.trim() || !form.full_name.trim()) return "Email and full name are required.";
    if (form.password.length < 8) return "Password must be at least 8 characters.";
    if (form.password.length > 72) return "Password must be 72 characters or fewer.";
    if (form.password !== form.confirm_password) return "Password confirmation does not match.";
    if (form.is_superuser && form.role !== "admin") return "Superuser accounts must use the Platform Admin global role.";
    return "";
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validation = validateCreateForm();
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await usersApi.create({
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        role: form.role,
        is_superuser: form.is_superuser,
      });
      setForm({ email: "", full_name: "", password: "", confirm_password: "", role: "qa_engineer", is_superuser: false });
      setNotice("User created successfully.");
      await loadUsersList();
    } catch (createError: any) {
      setError(messageFromError(createError, "Could not create user."));
    } finally {
      setSaving(false);
    }
  }

  async function updateUser(user: UserAccount, updates: Partial<UserAccount>) {
    setError("");
    setNotice("");
    try {
      await usersApi.update(user.id, updates);
      setNotice("User profile updated successfully.");
      await loadUsersList();
    } catch (updateError: any) {
      setError(messageFromError(updateError, "Could not update user profile."));
    }
  }

  async function assignMembership(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) {
      setError("Select a project before assigning a project role.");
      return;
    }
    if (!selectedUserId) {
      setError("Select a user before assigning a project role.");
      return;
    }
    if (!selectedProjectRole) {
      setError("Select a project RBAC role.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await projectsApi.addMembership(selectedProjectId, { user_id: selectedUserId, role: selectedProjectRole });
      setNotice("Project membership assigned successfully.");
      await loadMemberships(selectedProjectId);
    } catch (membershipError: any) {
      setError(messageFromError(membershipError, "Could not save project membership."));
    } finally {
      setSaving(false);
    }
  }

  async function disableMembership(membership: ProjectMembership) {
    if (!selectedProjectId) return;
    setError("");
    setNotice("");
    try {
      await projectsApi.removeMembership(selectedProjectId, membership.id);
      setNotice("Project membership disabled successfully.");
      await loadMemberships(selectedProjectId);
    } catch (membershipError: any) {
      setError(messageFromError(membershipError, "Could not disable membership."));
    }
  }

  const stats = useMemo(() => {
    return [
      {
        title: "Total Registered Users",
        icon: Users,
        iconBg: "bg-app-brand-75 border-app-brand-100",
        iconColor: "text-app-brand-505",
        value: users.length.toLocaleString(),
        sublabel: "Total",
        footer: "Total user records on platform",
      },
      {
        title: "Active Accounts",
        icon: CheckCircle2,
        iconBg: "bg-emerald-50 border-emerald-100",
        iconColor: "text-emerald-505",
        value: activeUsers.toLocaleString(),
        sublabel: "Active",
        footer: `${users.length > 0 ? ((activeUsers / users.length) * 100).toFixed(1) : "0.0"}% active user base`,
      },
      {
        title: "Platform Admins",
        icon: Shield,
        iconBg: "bg-app-brand-75 border-app-brand-100",
        iconColor: "text-app-brand-505",
        value: adminUsers.toLocaleString(),
        sublabel: "Admins",
        footer: `${users.length > 0 ? ((adminUsers / users.length) * 100).toFixed(1) : "0.0"}% privileged superusers`,
      },
    ];
  }, [users, activeUsers, adminUsers]);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-app-brand-75 border border-app-brand-100 p-2.5">
            <Users className="h-6 w-6 text-[#B71920]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">User Management</h1>
            <p className="text-xs text-gray-500 mt-1">Manage global user credentials, platform permission flags, and project-level RBAC role assignments</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh} className="h-8 border-gray-205 bg-white font-semibold text-gray-700">
            <RefreshCw className={cn("h-3.5 w-3.5 text-gray-500 mr-1.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {stats.map((card) => {
          const Icon = card.icon;
          return (
            <Card key={card.title} className="border-gray-200 hover:-translate-y-0.5 transition-all bg-white">
              <CardContent className="p-4 flex flex-col justify-between h-full space-y-3">
                <div className="flex items-center gap-2">
                  <div className={cn("rounded-lg p-1.5 flex items-center justify-center shrink-0 border", card.iconBg)}>
                    <Icon className={cn("h-4 w-4", card.iconColor)} />
                  </div>
                  <span className="text-xs font-bold text-gray-700 truncate">{card.title}</span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-gray-900">{card.value}</span>
                  {card.sublabel && (
                    <span className="text-[10px] font-bold text-gray-400">{card.sublabel}</span>
                  )}
                </div>
                <div className="text-[10px] text-gray-400 font-semibold border-t border-gray-50 pt-2">
                  {card.footer}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {error && (
        <div className="flex items-center gap-2.5 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-700">
          <AlertTriangle className="h-4 w-4 shrink-0 text-rose-500" />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="flex items-center gap-2.5 rounded-lg border border-emerald-250 bg-emerald-50 px-4 py-3 text-xs font-semibold text-emerald-700">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
          <span>{notice}</span>
        </div>
      )}
      {!isPlatformAdmin && (
        <div className="flex items-center gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-800">
          <Shield className="h-4 w-4 shrink-0 text-amber-600" />
          <span>Project managers can assign project roles here, but only platform admins can create accounts or change global user access.</span>
        </div>
      )}

      {/* ── Left form & Right Users Table Split ──────────────────────────────────── */}
      <div className={cn("grid gap-6", isPlatformAdmin ? "xl:grid-cols-[400px_1fr]" : "xl:grid-cols-1")}>
        
        {/* Create User Card */}
        {isPlatformAdmin ? (
        <Card className="border-gray-200 shadow-sm overflow-hidden bg-white h-fit">
          <div className="border-b px-5 py-4 border-gray-100 bg-gray-50/50">
            <div className="flex items-center gap-2">
              <UserPlus className="h-4 w-4 text-[#B71920]" />
              <h2 className="font-bold text-gray-800 text-xs uppercase tracking-wider">Create User Account</h2>
            </div>
          </div>
          <form onSubmit={handleCreateUser} className="space-y-4.5 p-5 text-xs font-semibold text-gray-750">
            <div className="space-y-1.5">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">Full Name</span>
              <input
                value={form.full_name}
                onChange={(event) => setForm((value) => ({ ...value, full_name: event.target.value }))}
                className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] transition-all bg-white"
                placeholder="e.g. Priya Raman"
              />
            </div>
            <div className="space-y-1.5">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">Email Address</span>
              <input
                type="email"
                value={form.email}
                onChange={(event) => setForm((value) => ({ ...value, email: event.target.value }))}
                className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] transition-all bg-white"
                placeholder="name@example.com"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">Password</span>
                <input
                  type="password"
                  value={form.password}
                  onChange={(event) => setForm((value) => ({ ...value, password: event.target.value }))}
                  className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] transition-all bg-white"
                />
              </div>
              <div className="space-y-1.5">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">Confirm</span>
                <input
                  type="password"
                  value={form.confirm_password}
                  onChange={(event) => setForm((value) => ({ ...value, confirm_password: event.target.value }))}
                  className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] transition-all bg-white"
                />
              </div>
            </div>
            <p className="text-[10px] text-gray-400 font-bold leading-relaxed">{PASSWORD_HINT}</p>
            
            <div className="space-y-1.5">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">Global Role Permission</span>
              <select
                value={form.role}
                onChange={(event) => setForm((value) => ({ 
                  ...value, 
                  role: event.target.value, 
                  is_superuser: event.target.value === "admin" ? value.is_superuser : false 
                }))}
                className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] bg-white cursor-pointer"
              >
                {GLOBAL_ROLES.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>
            </div>
            
            <label className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50/50 p-3 text-xs font-semibold cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_superuser}
                disabled={form.role !== "admin"}
                onChange={(event) => setForm((value) => ({ ...value, is_superuser: event.target.checked }))}
                className="mt-0.5 rounded border-gray-300 text-[#B71920] focus:ring-[#B71920]"
              />
              <span className="flex-1">
                <span className="font-bold text-gray-800">Platform Superuser flag</span>
                <span className="block text-[10px] text-gray-400 font-semibold mt-0.5 leading-normal">
                  Grants bypass rules and full database access. Enabled only for Platform Admin role.
                </span>
              </span>
            </label>
            
            <Button
              disabled={saving}
              variant="default"
              className="w-full items-center justify-center gap-2 bg-[#B71920] hover:bg-[#941216] text-white h-9"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin text-white" /> : <UserPlus className="h-4 w-4 mr-0.5" />}
              Create User Profile
            </Button>
          </form>
        </Card>
        ) : null}

        {/* Users Table List */}
        <Card className="border-gray-200 shadow-sm overflow-hidden bg-white">
          <div className="flex flex-col gap-3 border-b px-5 py-4 border-gray-100 bg-gray-50/50 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-[#B71920]" />
              <h2 className="font-bold text-gray-800 text-xs uppercase tracking-wider">Users Directory</h2>
            </div>
            <div className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold bg-white shadow-inner">
              <Search className="h-4 w-4 text-gray-400" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") loadUsersList();
                }}
                className="w-48 bg-transparent outline-none text-gray-850 font-semibold"
                placeholder="Search users..."
              />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-semibold select-none">
              <thead className="border-b border-gray-100 bg-gray-50/20 text-left text-[10px] font-bold uppercase tracking-wider text-gray-400">
                <tr>
                  <th className="px-4 py-3">User Profile</th>
                  <th className="px-4 py-3">Global Role</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Controls</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 text-gray-600 font-medium">
                {loading ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-16 text-center text-gray-400 font-semibold">
                      <RefreshCw className="inline mr-2 h-4 w-4 animate-spin text-[#B71920]" />
                      Loading users directory...
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-16 text-center text-gray-450 font-bold">No registered users found.</td>
                  </tr>
                ) : (
                  users.map((user) => (
                    <tr key={user.id} className="hover:bg-gray-50/30 transition-colors">
                      <td className="px-4 py-3">
                        <p className="font-bold text-gray-800 text-xs">{user.full_name}</p>
                        <p className="text-[10px] text-gray-400 font-mono font-bold mt-0.5">{user.email}</p>
                      </td>
                      <td className="px-4 py-3">
                        {isPlatformAdmin ? (
                          <select
                            value={user.role}
                            onChange={(event) => updateUser(user, { role: event.target.value })}
                            className="rounded-lg border border-gray-205 px-2 py-1 text-[11px] font-semibold bg-white cursor-pointer"
                          >
                            {GLOBAL_ROLES.map((role) => (
                              <option key={role.value} value={role.value}>
                                {role.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <Badge variant="secondary" className="text-[10px] font-bold uppercase tracking-wider">
                            {GLOBAL_ROLES.find((role) => role.value === user.role)?.label ?? user.role}
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <Badge variant={getStatusVariant(user.is_active)} className="capitalize text-[9px] py-0 px-2">
                            {user.is_active ? "Active" : "Inactive"}
                          </Badge>
                          {user.is_superuser && (
                            <Badge variant="default" className="bg-app-brand-75 text-app-brand-700 border border-app-brand-100 text-[9px] py-0 px-2 uppercase tracking-wider font-extrabold">
                              Superuser
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {isPlatformAdmin ? (
                          <div className="flex items-center justify-end gap-1.5 flex-wrap">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => updateUser(user, { is_active: !user.is_active })}
                              className="h-7 px-2.5 text-[10px] font-bold border-gray-200 bg-white"
                            >
                              {user.is_active ? "Deactivate" : "Activate"}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => updateUser(user, {
                                is_superuser: !user.is_superuser,
                                role: !user.is_superuser ? "admin" : user.role
                              })}
                              className="h-7 px-2.5 text-[10px] font-bold border-gray-200 bg-white"
                            >
                              {user.is_superuser ? "Revoke Super" : "Grant Super"}
                            </Button>
                          </div>
                        ) : (
                          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-350">Project role access only</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* ── Project RBAC Assignment Card ─────────────────────────────────────────── */}
      <Card className="border-gray-200 shadow-sm overflow-hidden bg-white">
        <div className="border-b px-5 py-4 border-gray-100 bg-gray-50/50">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-[#B71920]" />
            <h2 className="font-bold text-gray-800 text-xs uppercase tracking-wider">Project RBAC Memberships</h2>
          </div>
          <p className="mt-1 text-[11px] text-gray-450 font-bold leading-relaxed">
            Link dynamic team roles to localized project permissions. Adding a user already in the project overrides their existing role.
          </p>
        </div>
        
        <form onSubmit={assignMembership} className="grid gap-3 p-5 lg:grid-cols-[1fr_1fr_1fr_auto] items-end text-xs font-semibold text-gray-700">
          <div className="space-y-1.5">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">Target Project</span>
            <select
              value={selectedProjectId ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                const params = new URLSearchParams(searchParams.toString());
                params.set("project", val);
                router.push(`${pathname}?${params.toString()}`);
              }}
              className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] bg-white cursor-pointer"
            >
              {projects.length === 0 ? <option value="">No manageable projects</option> : null}
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
          
          <div className="space-y-1.5">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">Select User Account</span>
            <select
              value={selectedUserId ?? ""}
              onChange={(event) => setSelectedUserId(Number(event.target.value))}
              className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] bg-white cursor-pointer"
            >
              <option value="">Choose User...</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name} ({user.email})
                </option>
              ))}
            </select>
          </div>
          
          <div className="space-y-1.5">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400">RBAC Role Privilege</span>
            <select
              value={selectedProjectRole}
              onChange={(event) => setSelectedProjectRole(event.target.value)}
              className="w-full rounded-lg border border-gray-205 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-[#B71920] bg-white cursor-pointer"
            >
              {roles.map((role) => (
                <option key={role.role} value={role.role}>
                  {role.role}
                </option>
              ))}
            </select>
          </div>
          
          <Button
            disabled={saving || !selectedProjectId || !selectedUserId}
            variant="default"
            className="bg-[#B71920] hover:bg-[#941216] text-white h-9 px-5 shrink-0"
          >
            <KeyRound className="h-4 w-4 mr-1.5" />
            Assign Role
          </Button>
        </form>

        {/* Memberships Grid Section */}
        <div className="border-t border-gray-100 bg-gray-50/20 px-5 py-4">
          <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider select-none mb-3">
            {selectedProject ? selectedProject.name : "Project"} Active Memberships
          </h3>
          {membershipRows.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-200 bg-white p-8 text-center text-gray-400 font-semibold text-xs shadow-sm">
              No custom memberships defined for this project.
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {membershipRows.map((membership) => (
                <Card key={membership.id} className="border-gray-205 p-3.5 bg-white hover:shadow-sm transition-all flex flex-col justify-between space-y-2 select-none">
                  <div>
                    <p className="font-bold text-gray-800 text-xs">{membership.user?.full_name ?? `User #${membership.user_id}`}</p>
                    <p className="text-[10px] text-gray-400 font-mono font-bold mt-0.5">{membership.user?.email ?? "Unknown account email"}</p>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-t border-gray-50 pt-2.5 mt-1 text-[11px] font-semibold">
                    <span className="rounded bg-app-brand-75 border border-app-brand-100 text-app-brand-700 px-2 py-0.5 text-[10px] font-bold select-none capitalize">
                      {membership.role}
                    </span>
                    {membership.is_active && (
                      <Button
                        onClick={() => disableMembership(membership)}
                        variant="outline"
                        size="sm"
                        className="h-7 px-2.5 text-[10px] font-bold border-rose-200 hover:bg-rose-50 text-rose-600 bg-white"
                      >
                        Disable
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

export default function UserManagementPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-gray-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#B71920] mr-2" />
        Loading User Management...
      </div>
    }>
      <UserManagementContent />
    </Suspense>
  );
}
