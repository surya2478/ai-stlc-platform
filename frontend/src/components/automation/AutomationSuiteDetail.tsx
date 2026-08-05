"use client";

// UI-018 Automation Workspace — Automation Test Suite detail.
//
// Overview / Test Cases / Inherited Scope / Conflicts and Gaps / Execution
// Groups / Versions are live. The remaining contract tabs render disabled with
// the reason, because the entity behind each one does not exist yet.
//
// Inherited values are rendered as read-only rows carrying their source. There
// are deliberately no inputs over inherited data.

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Archive,
  ArrowLeft,
  ChevronRight,
  Download,
  Loader2,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
  UploadCloud,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  automationSuiteApi,
  type AutomationSuiteActivityEntry,
  type AutomationSuiteExecutionGroup,
  type AutomationSuiteGap,
  type AutomationSuiteImpactReview,
  type AutomationSuiteInheritedScope,
  type AutomationSuiteMember,
  type AutomationSuiteOverview,
  type AutomationSuiteVersion,
  type InheritedScopeItem,
  suiteExecutionApi,
  type SuiteRunListRow,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Banner,
  DisabledTab,
  EmptyRow,
  MemberStatusBadge,
  Panel,
  SeverityBadge,
  StatCard,
  SuiteStatusBadge,
  formatDateTime,
  humanizeCode,
  messageFromError,
} from "@/components/automation/suite-shared";
import { Layers3, ListChecks, AlertTriangle, FileCode2, GitBranch } from "lucide-react";
import { ExecutionPathList } from "@/components/test-cases/ExecutionPathPanel";

type LiveTab =
  | "overview"
  | "test-cases"
  | "inherited-scope"
  | "conflicts"
  | "execution-groups"
  | "versions"
  | "executions";

const LIVE_TABS: { key: LiveTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "test-cases", label: "Test Cases" },
  { key: "inherited-scope", label: "Inherited Scope" },
  { key: "conflicts", label: "Conflicts and Gaps" },
  { key: "execution-groups", label: "Execution Groups" },
  { key: "versions", label: "Versions" },
  // Live as of P1-S7: migration 052 gave execution_runs a snapshot link, so this
  // tab now launches and lists real runs rather than explaining its own absence.
  { key: "executions", label: "Executions" },
];

const DEFERRED_TABS: { label: string; reason: string }[] = [
  { label: "Automation Assets", reason: "No automation-asset entity exists yet" },
  { label: "Test Data", reason: "Suite-scoped test data selection is P1-S6" },
  {
    label: "Evidence",
    reason:
      "Per-run evidence is on the execution command center; the consolidated evidence report is UI-052",
  },
];

// Statuses whose scope is frozen by a publication snapshot.
const FROZEN_STATUSES = ["APPROVED", "PUBLISHED", "DEPRECATED", "ARCHIVED"];

const RESOLUTION_ACTIONS = [
  { value: "keep_per_test_case", label: "Keep configuration per test case" },
  { value: "apply_default_to_missing", label: "Apply default only where missing" },
  { value: "exclude_test_case", label: "Exclude this test case" },
  { value: "open_source", label: "Corrected at source" },
  { value: "send_for_mapping_review", label: "Send for mapping review" },
];

function SourceRow({ item, primary }: { item: InheritedScopeItem; primary: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-gray-50 py-1.5 last:border-0">
      <div className="min-w-0">
        <p className="truncate text-[11px] font-bold text-gray-800">{primary}</p>
        <p className="truncate text-[9px] font-semibold text-gray-400">{item.source}</p>
      </div>
      <Badge variant="outline" className="shrink-0 text-[8px]">
        {item.source_entity}
        {item.source_id !== null ? ` #${item.source_id}` : ""}
      </Badge>
    </div>
  );
}

export function AutomationSuiteDetail({
  projectId,
  suiteId,
}: {
  projectId: number;
  suiteId: number;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [tab, setTab] = useState<LiveTab>("overview");
  const [overview, setOverview] = useState<AutomationSuiteOverview | null>(null);
  const [members, setMembers] = useState<AutomationSuiteMember[]>([]);
  const [gaps, setGaps] = useState<AutomationSuiteGap[]>([]);
  const [scope, setScope] = useState<AutomationSuiteInheritedScope | null>(null);
  const [activity, setActivity] = useState<AutomationSuiteActivityEntry[]>([]);
  const [groups, setGroups] = useState<AutomationSuiteExecutionGroup[]>([]);
  const [groupMeta, setGroupMeta] = useState<{
    split_dimensions: string[];
    unavailable: Record<string, string>;
  }>({ split_dimensions: [], unavailable: {} });
  const [versions, setVersions] = useState<AutomationSuiteVersion[]>([]);
  const [impact, setImpact] = useState<AutomationSuiteImpactReview | null>(null);
  const [runs, setRuns] = useState<SuiteRunListRow[]>([]);
  const [launching, setLaunching] = useState(false);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const [overviewRes, membersRes, gapsRes, scopeRes, activityRes, groupsRes, versionsRes, impactRes] =
      await Promise.all([
        automationSuiteApi.getSuite(suiteId),
        automationSuiteApi.members(suiteId, { page_size: 100 }),
        automationSuiteApi.gaps(suiteId, { page_size: 100 }),
        automationSuiteApi.inheritedScope(suiteId),
        automationSuiteApi.activity(suiteId, { page_size: 20 }).catch(() => null),
        automationSuiteApi.executionGroups(suiteId).catch(() => null),
        automationSuiteApi.versions(suiteId).catch(() => null),
        automationSuiteApi.impactReview(suiteId).catch(() => null),
      ]);
    // Tolerated separately: a user with suite access but without
    // execution.view_live_runs should still see the rest of the suite rather than
    // have the whole detail view fail on a 403.
    const runsRes = await suiteExecutionApi.listForSuite(suiteId).catch(() => null);
    setRuns(runsRes?.data ?? []);
    setOverview(overviewRes.data);
    setMembers(membersRes.data.items);
    setGaps(gapsRes.data.items);
    setScope(scopeRes.data);
    setActivity(activityRes?.data.items ?? []);
    setGroups(groupsRes?.data.items ?? []);
    setGroupMeta({
      split_dimensions: groupsRes?.data.split_dimensions ?? [],
      unavailable: groupsRes?.data.unavailable ?? {},
    });
    setVersions(versionsRes?.data.items ?? []);
    setImpact(impactRes?.data ?? null);
  }, [suiteId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    load()
      .catch((err) => {
        if (active) setError(messageFromError(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [load]);

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(successMessage);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setBusy(false);
    }
  };

  const backToList = () => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", "workspace");
    params.delete("suite");
    router.push(`/automation?${params.toString()}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-xs font-bold text-gray-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#B71920]" />
        Loading suite...
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="space-y-3">
        {error && <Banner kind="error" message={error} />}
        <Button size="sm" variant="outline" onClick={backToList}>
          <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
          Back to Automation Workspace
        </Button>
      </div>
    );
  }

  const openGaps = gaps.filter((g) => g.status === "open");
  const adjudicated = gaps.filter((g) => g.status !== "open");

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-500">
            <button type="button" onClick={backToList} className="hover:text-[#B71920]">
              Automation Studio
            </button>
            <ChevronRight className="h-3 w-3 text-gray-300" />
            <button type="button" onClick={backToList} className="hover:text-[#B71920]">
              Automation Workspace
            </button>
            <ChevronRight className="h-3 w-3 text-gray-300" />
            <span className="truncate text-gray-800">{overview.name}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-gray-900">{overview.name}</h1>
            <SuiteStatusBadge status={overview.status} />
            {overview.default_environment ? (
              <Badge variant="outline" className="text-[9px]">
                {overview.default_environment}
              </Badge>
            ) : (
              <Badge variant="warning" className="text-[9px]">
                No environment set
              </Badge>
            )}
          </div>
          {overview.description && (
            <p className="mt-1 text-xs font-semibold text-gray-500">{overview.description}</p>
          )}
          <p className="mt-1 text-[10px] font-semibold text-gray-400">
            Last evaluated {formatDateTime(overview.last_evaluated_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={backToList}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
            All suites
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || overview.status === "ARCHIVED"}
            onClick={() =>
              run(() => automationSuiteApi.evaluate(suiteId), "Inherited scope refreshed and re-evaluated.")
            }
          >
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", busy && "animate-spin")} />
            Refresh inherited scope
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => window.open(automationSuiteApi.exportUrl(suiteId), "_blank")}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Export
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || overview.status === "ARCHIVED"}
            onClick={() => run(() => automationSuiteApi.archive(suiteId), "Suite archived.")}
          >
            <Archive className="mr-1.5 h-3.5 w-3.5" />
            Archive
          </Button>
        </div>
      </header>

      {/* ── Approval workflow. Only the transition the suite is actually at is offered. ── */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 bg-gray-50/70 px-3 py-2.5">
        <span className="text-[10px] font-extrabold uppercase tracking-wide text-gray-500">
          Approval
        </span>
        {overview.status === "READY_FOR_VALIDATION" || overview.status === "INHERITANCE_REVIEW_REQUIRED" ? (
          <Button
            size="sm"
            disabled={busy}
            onClick={() =>
              run(() => automationSuiteApi.submitForReview(suiteId), "Suite submitted for review.")
            }
          >
            <Send className="mr-1.5 h-3.5 w-3.5" />
            Submit for review
          </Button>
        ) : overview.status === "READY_FOR_REVIEW" ? (
          <>
            <Button
              size="sm"
              disabled={busy}
              onClick={() =>
                run(
                  () => automationSuiteApi.approveSuite(suiteId, "Scope verified"),
                  "Suite approved.",
                )
              }
            >
              <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
              Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => {
                const reason = window.prompt("What needs to change before this suite can be approved?");
                if (!reason?.trim()) return;
                run(
                  () => automationSuiteApi.requestChanges(suiteId, reason),
                  "Changes requested — the suite is back with its author.",
                );
              }}
            >
              Request changes
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => {
                const reason = window.prompt("Why is this suite being rejected?");
                if (!reason?.trim()) return;
                run(() => automationSuiteApi.rejectSuite(suiteId, reason), "Suite rejected.");
              }}
            >
              Reject
            </Button>
            <span className="text-[10px] font-semibold text-gray-500">
              The user who submitted it cannot also approve it.
            </span>
          </>
        ) : overview.status === "APPROVED" ? (
          <Button
            size="sm"
            disabled={busy}
            onClick={() =>
              run(
                () => automationSuiteApi.publishSuite(suiteId),
                "Suite published — an immutable snapshot was recorded.",
              )
            }
          >
            <UploadCloud className="mr-1.5 h-3.5 w-3.5" />
            Publish
          </Button>
        ) : FROZEN_STATUSES.includes(overview.status) ? (
          <>
            <span className="text-[10px] font-semibold text-gray-500">
              This version is frozen by its publication snapshot.
            </span>
            {overview.status !== "ARCHIVED" && (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  run(
                    () => automationSuiteApi.newVersion(suiteId),
                    "A new draft version was created from this one.",
                  )
                }
              >
                <GitBranch className="mr-1.5 h-3.5 w-3.5" />
                Start new version
              </Button>
            )}
          </>
        ) : (
          <span className="text-[10px] font-semibold text-gray-500">
            Resolve the open critical findings to submit this suite for review.
          </span>
        )}
      </div>

      {impact?.impact_review_required && (
        <Banner
          kind="info"
          message={`Impact review: ${impact.changed_members?.length ?? 0} member(s) changed at source since version ${impact.snapshot?.suite_version} was published. The published version and its results are unchanged — start a new version to adopt the changes.`}
        />
      )}

      {error && <Banner kind="error" message={error} onDismiss={() => setError(null)} />}
      {notice && <Banner kind="info" message={notice} onDismiss={() => setNotice(null)} />}

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        <StatCard
          title="Test Cases"
          value={overview.members_included}
          subtitle={`${overview.members_manual_only} manual-only · ${overview.members_total} total`}
          icon={ListChecks}
          tone="blue"
        />
        <StatCard
          title="Automated Coverage"
          value={`${overview.automation_coverage_pct}%`}
          subtitle={`${overview.automated_members} of ${overview.members_included} have a script`}
          icon={FileCode2}
          tone="emerald"
        />
        <StatCard
          title="Critical Gaps"
          value={overview.gaps_critical_open}
          subtitle={`${overview.gaps_warning_open} warnings`}
          icon={AlertTriangle}
          tone={overview.gaps_critical_open > 0 ? "red" : "emerald"}
        />
        <StatCard
          title="Conflicts"
          value={overview.conflicts_open}
          subtitle="Across selected test cases"
          icon={GitBranch}
          tone={overview.conflicts_open > 0 ? "amber" : "emerald"}
        />
        <StatCard
          title="Execution Groups"
          value={overview.execution_group_count}
          subtitle=""
          icon={Layers3}
          tone="purple"
          unavailableReason="Execution groups are not configured for this suite"
        />
      </div>

      {/* ── Tabs ── */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-gray-200">
        {LIVE_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              "whitespace-nowrap border-b-2 px-2.5 py-2 text-[10px] font-bold transition",
              tab === t.key
                ? "border-[#B71920] text-[#B71920]"
                : "border-transparent text-gray-500 hover:text-gray-800",
            )}
          >
            {t.label}
            {t.key === "conflicts" && openGaps.length > 0 && (
              <span className="ml-1 rounded-full bg-red-50 px-1.5 py-0.5 text-[8px] font-extrabold text-red-600">
                {openGaps.length}
              </span>
            )}
          </button>
        ))}
        {DEFERRED_TABS.map((t) => (
          <DisabledTab key={t.label} label={t.label} reason={t.reason} />
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_320px]">
          {/* Suite gaps only cover what a suite owns. Blockers upstream of it —
              an unapproved requirement, a missing discovery session, a model
              awaiting review — are invisible here, and were previously found
              only by hitting them in another module. */}
          <Panel title="Path to Execution">
            <ExecutionPathList
              projectId={projectId}
              testCases={members.map((m) => ({
                id: m.test_case_id,
                label: m.test_case_reference || `TC-${m.test_case_id}`,
              }))}
              emptyMessage="This suite has no members yet."
            />
          </Panel>

          <Panel title="Readiness Summary">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[10px] font-semibold">
              {[
                ["Members ready", overview.members_ready],
                ["Members blocked", overview.members_blocked],
                ["Members drifted from source", overview.members_drifted],
                ["Inherited applications", overview.inherited_application_count],
                ["Linked scripts", overview.linked_script_count],
                [
                  "Inherited frameworks",
                  overview.inherited_frameworks.length > 0
                    ? overview.inherited_frameworks.join(", ")
                    : "None",
                ],
                ["Last inheritance sync", formatDateTime(overview.last_inheritance_sync_at)],
              ].map(([label, value]) => (
                <div key={String(label)} className="flex items-center justify-between gap-2">
                  <dt className="text-gray-500">{label}</dt>
                  <dd className="font-extrabold text-gray-900">{value}</dd>
                </div>
              ))}
              <div className="flex items-center justify-between gap-2">
                <dt className="text-gray-500">Validation</dt>
                <dd className="text-gray-300" title={overview.unavailable.validation_summary}>
                  Not available
                </dd>
              </div>
            </dl>
          </Panel>
          <Panel title="Recent Activity">
            {activity.length === 0 ? (
              <p className="py-6 text-center text-[10px] font-semibold text-gray-400">
                No activity recorded yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {activity.slice(0, 12).map((entry) => (
                  <li key={entry.id} className="border-b border-gray-50 pb-1.5 last:border-0">
                    <p className="text-[10px] font-bold text-gray-800">
                      {humanizeCode(entry.event_type)}
                    </p>
                    <p className="text-[9px] font-semibold text-gray-400">
                      {formatDateTime(entry.created_at)}
                      {entry.reason ? ` · ${entry.reason}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      )}

      {tab === "test-cases" && (
        <Panel title={`Test Cases (${members.length})`}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[10px]">
              <thead>
                <tr className="border-b border-gray-100 text-[9px] font-extrabold uppercase text-gray-400">
                  <th className="py-1.5">Test Case</th>
                  <th>Title</th>
                  <th>Approval</th>
                  <th>Mode</th>
                  <th>Framework</th>
                  <th>Environment</th>
                  <th>Readiness</th>
                  <th>Scope</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-1.5 font-bold text-gray-800">
                      {member.test_case_reference ?? `TC-${member.test_case_id}`}
                    </td>
                    <td className="max-w-[260px] truncate font-semibold text-gray-600">
                      {member.title ?? "—"}
                      {member.source_reference && (
                        <span className="ml-1 text-[9px] font-semibold text-gray-400">
                          ({member.source_reference})
                        </span>
                      )}
                    </td>
                    <td className="font-semibold text-gray-600">{member.test_case_status ?? "—"}</td>
                    <td className="font-semibold text-gray-600">{member.execution_mode ?? "—"}</td>
                    <td className="font-semibold text-gray-600">
                      {member.resolved_framework ?? (
                        <span className="text-gray-300" title="No active script for this test case">
                          —
                        </span>
                      )}
                    </td>
                    <td className="font-semibold text-gray-600">
                      {member.resolved_environment ?? (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="font-semibold text-gray-600">
                      {member.readiness_checks_total > 0
                        ? `${member.readiness_checks_passed}/${member.readiness_checks_total}`
                        : "—"}
                    </td>
                    <td>
                      <span className="flex flex-col gap-0.5">
                        <MemberStatusBadge status={member.member_status} />
                        {member.inclusion_status !== "included" && (
                          <Badge variant="outline" className="w-fit text-[8px]">
                            {humanizeCode(member.inclusion_status)}
                          </Badge>
                        )}
                      </span>
                    </td>
                    <td className="text-right">
                      {/* UI-020/021/023 entry point — opens the Automation Asset
                          Workspace for this member on its IR Editor tab. */}
                      <a
                        href={`/automation?view=ir&member=${member.id}`}
                        className="mr-2 text-[9px] font-bold text-[#B71920] hover:underline"
                      >
                        Open asset
                      </a>
                      {member.inclusion_status === "included" ? (
                        <button
                          type="button"
                          disabled={busy || overview.status === "ARCHIVED"}
                          onClick={() =>
                            run(
                              () =>
                                automationSuiteApi.updateMember(suiteId, member.id, {
                                  inclusion_status: "excluded",
                                  exclusion_reason: "Excluded from the suite by a reviewer.",
                                }),
                              "Test case excluded from this suite.",
                            )
                          }
                          className="text-[9px] font-bold text-gray-500 hover:text-red-600 disabled:text-gray-300"
                        >
                          Exclude
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={busy || overview.status === "ARCHIVED"}
                          onClick={() =>
                            run(
                              () =>
                                automationSuiteApi.updateMember(suiteId, member.id, {
                                  inclusion_status: "included",
                                }),
                              "Test case included again.",
                            )
                          }
                          className="text-[9px] font-bold text-gray-500 hover:text-[#B71920] disabled:text-gray-300"
                        >
                          Include
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {members.length === 0 && (
                  <EmptyRow colSpan={9} message="This suite has no test cases yet." />
                )}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[9px] font-semibold text-gray-400">
            Test case metadata is owned by Test Management and is read-only here.
          </p>
        </Panel>
      )}

      {tab === "inherited-scope" && scope && (
        <div className="space-y-3">
          <p className="text-[10px] font-semibold text-gray-500">
            Everything below is inherited from its authoritative source and cannot be edited here.
            Last synchronized {formatDateTime(scope.last_synchronized_at)}.
          </p>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Panel title={`Business Traceability (${scope.business_traceability.length})`}>
              {scope.business_traceability.length === 0 ? (
                <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                  No test cases in scope.
                </p>
              ) : (
                scope.business_traceability.map((item, i) => (
                  <SourceRow
                    key={i}
                    item={item}
                    primary={`${item.test_case_reference ?? `TC-${item.test_case_id}`} — ${
                      (item.title as string) ?? "Untitled"
                    }`}
                  />
                ))
              )}
            </Panel>
            <Panel title={`Applications (${scope.applications.length})`}>
              {scope.applications.length === 0 ? (
                <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                  No application resolved for any member.
                </p>
              ) : (
                scope.applications.map((item, i) => (
                  <SourceRow
                    key={i}
                    item={item}
                    primary={`${item.name as string} — model ${
                      (item.model_status as string) ?? "not built"
                    }`}
                  />
                ))
              )}
            </Panel>
            <Panel title={`Frameworks (${scope.frameworks.length})`}>
              {scope.frameworks.length === 0 ? (
                <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                  No frameworks inherited — no active scripts in scope.
                </p>
              ) : (
                scope.frameworks.map((item, i) => (
                  <SourceRow
                    key={i}
                    item={item}
                    primary={`${item.framework as string} — ${item.script_count as number} script(s)`}
                  />
                ))
              )}
              <p className="mt-1.5 text-[9px] font-semibold text-gray-400">
                {scope.unavailable.framework_profiles}
              </p>
            </Panel>
            <Panel title={`Scripts (${scope.scripts.length})`}>
              {scope.scripts.length === 0 ? (
                <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                  No automation scripts linked yet.
                </p>
              ) : (
                scope.scripts.map((item, i) => (
                  <SourceRow
                    key={i}
                    item={item}
                    primary={`${(item.script_reference as string) ?? (item.file_path as string)} (${
                      item.framework as string
                    })`}
                  />
                ))
              )}
              <p className="mt-1.5 text-[9px] font-semibold text-gray-400">
                {scope.unavailable.automation_ir}
              </p>
            </Panel>
            <Panel title={`Environments (${scope.environments.length})`}>
              {scope.environments.length === 0 ? (
                <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                  No environment set for this suite.
                </p>
              ) : (
                scope.environments.map((item, i) => (
                  <SourceRow
                    key={i}
                    item={item}
                    primary={`${item.environment as string} — ${
                      item.url_configured ? "URL configured" : "no URL configured"
                    }`}
                  />
                ))
              )}
            </Panel>
            <Panel title={`Test Data (${scope.test_data.length})`}>
              {scope.test_data.length === 0 ? (
                <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                  No test data linked to these test cases.
                </p>
              ) : (
                scope.test_data.map((item, i) => (
                  <SourceRow
                    key={i}
                    item={item}
                    primary={`${(item.reference as string) ?? (item.name as string)} (${
                      (item.environment as string) ?? "no environment"
                    })`}
                  />
                ))
              )}
            </Panel>
          </div>
          <Panel title="Not Inherited">
            <ul className="space-y-1 text-[10px] font-semibold text-gray-500">
              {Object.entries(scope.unavailable).map(([field, reason]) => (
                <li key={field} className="flex gap-2">
                  <span className="shrink-0 font-bold text-gray-700">{humanizeCode(field)}:</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}

      {tab === "conflicts" && (
        <div className="space-y-3">
          <Panel title={`Open Findings (${openGaps.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[10px]">
                <thead>
                  <tr className="border-b border-gray-100 text-[9px] font-extrabold uppercase text-gray-400">
                    <th className="py-1.5">Finding</th>
                    <th>Kind</th>
                    <th>Severity</th>
                    <th>Stage</th>
                    <th>Detail</th>
                    <th>Resolve</th>
                  </tr>
                </thead>
                <tbody>
                  {openGaps.map((gap) => (
                    <tr key={gap.id} className="border-b border-gray-50 align-top">
                      <td className="py-1.5 font-bold text-gray-800">
                        {humanizeCode(gap.gap_type)}
                        <span className="mt-0.5 block text-[9px] font-semibold text-gray-400">
                          {gap.scope === "suite"
                            ? "Across the suite"
                            : `TC-${gap.test_case_id ?? "?"}`}
                        </span>
                      </td>
                      <td>
                        <Badge
                          variant={gap.category === "conflict" ? "purple" : "secondary"}
                          className="text-[8px]"
                        >
                          {gap.category === "conflict" ? "Conflict" : "Gap"}
                        </Badge>
                      </td>
                      <td>
                        <SeverityBadge severity={gap.severity} />
                      </td>
                      <td className="font-semibold text-gray-500">{humanizeCode(gap.stage)}</td>
                      <td className="max-w-[320px] font-semibold text-gray-600">
                        {gap.reason}
                        {gap.remediation && (
                          <span className="mt-0.5 block text-[9px] font-semibold text-gray-400">
                            {gap.remediation}
                          </span>
                        )}
                      </td>
                      <td className="min-w-[190px]">
                        <div className="flex flex-col gap-1">
                          <select
                            defaultValue=""
                            disabled={busy || overview.status === "ARCHIVED"}
                            onChange={(e) => {
                              const action = e.target.value;
                              e.target.value = "";
                              if (!action) return;
                              run(
                                () =>
                                  automationSuiteApi.resolveGap(suiteId, gap.id, {
                                    resolution_action: action,
                                  }),
                                "Finding resolved.",
                              );
                            }}
                            className="h-7 rounded-md border border-gray-200 px-1.5 text-[9px] font-bold"
                          >
                            <option value="">Choose resolution...</option>
                            {RESOLUTION_ACTIONS.filter(
                              (a) => a.value !== "exclude_test_case" || gap.suite_test_case_id !== null,
                            ).map((a) => (
                              <option key={a.value} value={a.value}>
                                {a.label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            disabled={busy || overview.status === "ARCHIVED"}
                            onClick={() => {
                              const reason = window.prompt(
                                "Why is this finding being waived? A reason is required and is recorded in the approval log.",
                              );
                              if (!reason?.trim()) return;
                              run(
                                () => automationSuiteApi.approveException(suiteId, gap.id, reason),
                                "Exception approved and recorded.",
                              );
                            }}
                            className="flex items-center gap-1 text-[9px] font-bold text-amber-600 hover:text-amber-700 disabled:text-gray-300"
                          >
                            <ShieldCheck className="h-3 w-3" />
                            Approve exception
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {openGaps.length === 0 && (
                    <EmptyRow
                      colSpan={6}
                      message="No open findings. Every member passed the readiness checks that could be evaluated."
                    />
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          {adjudicated.length > 0 && (
            <Panel title={`Resolved and Waived (${adjudicated.length})`}>
              <table className="w-full text-left text-[10px]">
                <thead>
                  <tr className="border-b border-gray-100 text-[9px] font-extrabold uppercase text-gray-400">
                    <th className="py-1.5">Finding</th>
                    <th>Outcome</th>
                    <th>Decision</th>
                    <th>Notes</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {adjudicated.map((gap) => (
                    <tr key={gap.id} className="border-b border-gray-50">
                      <td className="py-1.5 font-bold text-gray-700">
                        {humanizeCode(gap.gap_type)}
                      </td>
                      <td>
                        <Badge
                          variant={gap.status === "exception_approved" ? "warning" : "success"}
                          className="text-[8px]"
                        >
                          {humanizeCode(gap.status)}
                        </Badge>
                      </td>
                      <td className="font-semibold text-gray-500">
                        {gap.auto_closed
                          ? "Closed automatically — no longer detected"
                          : gap.resolution_action
                            ? humanizeCode(gap.resolution_action)
                            : "—"}
                      </td>
                      <td className="max-w-[240px] font-semibold text-gray-500">
                        {gap.reviewer_notes ?? "—"}
                      </td>
                      <td className="font-semibold text-gray-400">
                        {formatDateTime(gap.resolved_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}

          <p className="text-[9px] font-semibold text-gray-400">
            Duplicate test cases cannot occur — suite membership is unique per test case. Framework
            and application pairing is not validated because no pairing rules exist in this
            platform.
          </p>
        </div>
      )}

      {tab === "execution-groups" && (
        <div className="space-y-3">
          <Panel
            title={`Execution Groups (${groups.filter((g) => g.id !== null).length})`}
            action={
              <div className="flex items-center gap-2">
                <select
                  defaultValue=""
                  disabled={busy || FROZEN_STATUSES.includes(overview.status)}
                  onChange={(e) => {
                    const dimension = e.target.value;
                    e.target.value = "";
                    if (!dimension) return;
                    run(
                      () => automationSuiteApi.splitExecutionGroups(suiteId, dimension),
                      `Suite split into groups by ${dimension}.`,
                    );
                  }}
                  className="h-7 rounded-md border border-gray-200 px-1.5 text-[9px] font-bold"
                >
                  <option value="">Auto-split by...</option>
                  {groupMeta.split_dimensions.map((d) => (
                    <option key={d} value={d}>
                      {humanizeCode(d)}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={busy || FROZEN_STATUSES.includes(overview.status)}
                  onClick={() => {
                    const name = window.prompt("Name for the new execution group?");
                    if (!name?.trim()) return;
                    run(
                      () => automationSuiteApi.createExecutionGroup(suiteId, { name }),
                      "Execution group created.",
                    );
                  }}
                  className="text-[9px] font-bold text-[#B71920] disabled:text-gray-300"
                >
                  + Add group
                </button>
              </div>
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[10px]">
                <thead>
                  <tr className="border-b border-gray-100 text-[9px] font-extrabold uppercase text-gray-400">
                    <th className="py-1.5">#</th>
                    <th>Group</th>
                    <th>Framework</th>
                    <th>Environment</th>
                    <th>Test Cases</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {groups.map((group) => (
                    <tr
                      key={group.id ?? "ungrouped"}
                      className={cn(
                        "border-b border-gray-50",
                        group.id === null && "bg-amber-50/40",
                      )}
                    >
                      <td className="py-1.5 font-semibold text-gray-400">
                        {group.id === null ? "—" : group.sequence}
                      </td>
                      <td className="font-bold text-gray-800">
                        {group.name}
                        {group.notes && (
                          <span className="mt-0.5 block text-[9px] font-semibold text-gray-400">
                            {group.notes}
                          </span>
                        )}
                      </td>
                      <td className="font-semibold text-gray-600">{group.framework ?? "—"}</td>
                      <td className="font-semibold text-gray-600">{group.environment ?? "—"}</td>
                      <td className="font-bold text-gray-700">{group.member_count}</td>
                      <td>
                        <Badge variant="outline" className="text-[8px]">
                          {humanizeCode(group.status)}
                        </Badge>
                      </td>
                      <td className="text-right">
                        {group.id !== null && (
                          <button
                            type="button"
                            disabled={busy || FROZEN_STATUSES.includes(overview.status)}
                            onClick={() =>
                              run(
                                () => automationSuiteApi.deleteExecutionGroup(suiteId, group.id as number),
                                "Execution group deleted.",
                              )
                            }
                            className="text-gray-300 hover:text-red-500 disabled:text-gray-200"
                            aria-label={`Delete ${group.name}`}
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {groups.length === 0 && (
                    <EmptyRow
                      colSpan={7}
                      message="No execution groups yet. Auto-split the suite by framework or environment, or add a group manually."
                    />
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Orchestration Policy">
            <ul className="space-y-1 text-[10px] font-semibold text-gray-500">
              {Object.entries(groupMeta.unavailable).map(([field, reason]) => (
                <li key={field} className="flex gap-2">
                  <span className="shrink-0 font-bold text-gray-700">{humanizeCode(field)}:</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}

      {tab === "versions" && (
        <div className="space-y-3">
          <Panel title={`Versions (${versions.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[10px]">
                <thead>
                  <tr className="border-b border-gray-100 text-[9px] font-extrabold uppercase text-gray-400">
                    <th className="py-1.5">Version</th>
                    <th>Status</th>
                    <th>Test Cases</th>
                    <th>Published</th>
                    <th>Snapshot</th>
                    <th>Decision</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {versions.map((v) => (
                    <tr
                      key={v.suite_id}
                      className={cn("border-b border-gray-50", v.suite_id === suiteId && "bg-app-brand-75/40")}
                    >
                      <td className="py-1.5 font-bold text-gray-800">
                        v{v.version}
                        {v.is_current && (
                          <Badge variant="info" className="ml-1.5 text-[8px]">
                            Current
                          </Badge>
                        )}
                      </td>
                      <td>
                        <SuiteStatusBadge status={v.status} />
                      </td>
                      <td className="font-semibold text-gray-600">{v.members_included}</td>
                      <td className="font-semibold text-gray-500">{formatDateTime(v.published_at)}</td>
                      <td className="font-mono text-[9px] font-semibold text-gray-500">
                        {v.snapshot_checksum ? (
                          <span title={v.snapshot_checksum}>{v.snapshot_checksum.slice(0, 12)}…</span>
                        ) : (
                          <span className="text-gray-300" title="Only published versions have a snapshot">
                            —
                          </span>
                        )}
                      </td>
                      <td className="max-w-[200px] truncate font-semibold text-gray-500">
                        {v.decision_reason ?? "—"}
                      </td>
                      <td className="text-right">
                        {v.suite_id !== suiteId && (
                          <button
                            type="button"
                            onClick={() => {
                              const params = new URLSearchParams(searchParams.toString());
                              params.set("view", "workspace");
                              params.set("suite", String(v.suite_id));
                              router.push(`/automation?${params.toString()}`);
                            }}
                            className="text-[9px] font-bold text-[#B71920]"
                          >
                            Open
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {versions.length === 0 && (
                    <EmptyRow colSpan={7} message="This suite has only its current version." />
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Publication Snapshot">
            {impact?.snapshot ? (
              <dl className="space-y-1.5 text-[10px] font-semibold">
                <div className="flex items-center justify-between">
                  <dt className="text-gray-500">Published version</dt>
                  <dd className="font-extrabold text-gray-900">v{impact.snapshot.suite_version}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-gray-500">Frozen test cases</dt>
                  <dd className="font-extrabold text-gray-900">{impact.snapshot.member_count}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="shrink-0 text-gray-500">Checksum</dt>
                  <dd className="truncate font-mono text-[9px] text-gray-600">
                    {impact.snapshot.checksum}
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-gray-500">Impact review</dt>
                  <dd
                    className={cn(
                      "font-extrabold",
                      impact.impact_review_required ? "text-amber-600" : "text-emerald-600",
                    )}
                  >
                    {impact.impact_review_required
                      ? `${impact.changed_members?.length ?? 0} member(s) changed at source`
                      : "In sync with sources"}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                {impact?.reason ?? "This version has not been published, so it has no snapshot."}
              </p>
            )}
            {impact?.changed_members && impact.changed_members.length > 0 && (
              <ul className="mt-2 space-y-1 border-t border-gray-100 pt-2">
                {impact.changed_members.map((c) => (
                  <li key={c.member_id} className="text-[10px] font-semibold text-gray-600">
                    <span className="font-bold text-gray-800">TC-{c.test_case_id}</span>{" "}
                    {c.reasons.join(" ")}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      )}

      {tab === "executions" && (
        <div className="space-y-3">
          <Panel title="Suite Execution">
            {overview?.status !== "PUBLISHED" ? (
              <p className="py-3 text-[10px] font-semibold text-gray-500">
                Only a published suite can be executed — a run is dispatched against
                the immutable publication snapshot, not against live scope. This
                suite is {overview?.status ?? "not loaded"}.
              </p>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-2 py-1">
                <p className="max-w-2xl text-[10px] font-semibold text-gray-600">
                  A run evaluates environment, application, data, framework and
                  worker readiness before dispatching anything. If a readiness axis
                  fails, the run is created and blocked with the reason rather than
                  started.
                </p>
                <button
                  type="button"
                  disabled={launching}
                  onClick={async () => {
                    setLaunching(true);
                    setError(null);
                    try {
                      const { data } = await suiteExecutionApi.start(suiteId, {});
                      // Straight into the command center: the gate verdict is
                      // already computed, so there is nothing to wait for here.
                      router.push(
                        `/automation/executions/${data.id}/live?project=${projectId}`,
                      );
                    } catch (caught) {
                      setError(messageFromError(caught));
                    } finally {
                      setLaunching(false);
                    }
                  }}
                  className="rounded-md bg-[#B71920] px-3 py-1.5 text-[10px] font-bold text-white disabled:opacity-50"
                >
                  {launching ? "Starting…" : "Start execution"}
                </button>
              </div>
            )}
          </Panel>

          <Panel title="Runs">
            {runs.length === 0 ? (
              // EmptyRow is a table row; this list is not a table, so the plain
              // paragraph is the correct element here.
              <p className="py-4 text-center text-[10px] font-semibold text-gray-400">
                This suite has not been executed yet.
              </p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {runs.map((run) => (
                  <li key={run.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <button
                        type="button"
                        onClick={() =>
                          router.push(
                            `/automation/executions/${run.id}/live?project=${projectId}`,
                          )
                        }
                        className="text-[11px] font-bold text-[#B71920] hover:underline"
                      >
                        {run.execution_id}
                      </button>
                      <p className="text-[9px] font-semibold text-gray-400">
                        {run.environment ?? "No environment"} ·{" "}
                        {run.started_at ? formatDateTime(run.started_at) : "not started"}
                        {run.execution_purpose ? ` · ${run.execution_purpose}` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 text-[9px] font-bold">
                      <span className="text-gray-500">
                        {run.passed}/{run.total_tests} passed
                      </span>
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-600">
                        {run.outcome ?? run.lifecycle_state ?? "—"}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
