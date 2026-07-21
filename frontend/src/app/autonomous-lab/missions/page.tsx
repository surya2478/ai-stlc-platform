"use client";

import Link from "next/link";
import {
  Bell,
  Bot,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  FileText,
  Lock,
  PauseCircle,
  Play,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple";

const metrics = [
  {
    title: "Requirements",
    value: "2",
    suffix: "Total",
    note: "100% analyzed",
    badge: "Approved",
    badgeVariant: "success" as BadgeVariant,
    icon: FileText,
    tone: "bg-blue-50 text-blue-600",
  },
  {
    title: "Test Cases",
    value: "156",
    suffix: "Total",
    note: "78% approved",
    badge: "Pending Review",
    badgeVariant: "warning" as BadgeVariant,
    icon: ClipboardCheck,
    tone: "bg-amber-50 text-amber-600",
  },
  {
    title: "Discovery",
    value: "3",
    suffix: "Applications",
    note: "2 sessions completed",
    badge: "Ready",
    badgeVariant: "success" as BadgeVariant,
    icon: Search,
    tone: "bg-emerald-50 text-emerald-600",
  },
  {
    title: "Automation",
    value: "64%",
    suffix: "Automation Ready",
    note: "IR validated",
    badge: "In Progress",
    badgeVariant: "info" as BadgeVariant,
    icon: Sparkles,
    tone: "bg-blue-50 text-[#1b59f8]",
  },
  {
    title: "Execution",
    value: "12",
    suffix: "Runs",
    note: "8 running / 4 queued",
    badge: "In Progress",
    badgeVariant: "purple" as BadgeVariant,
    icon: Play,
    tone: "bg-violet-50 text-violet-600",
  },
  {
    title: "Evidence",
    value: "85%",
    suffix: "Quorum Met",
    note: "2 incomplete",
    badge: "Good",
    badgeVariant: "success" as BadgeVariant,
    icon: Shield,
    tone: "bg-emerald-50 text-emerald-600",
  },
];

const lifecycle = [
  {
    title: "Requirement Intelligence",
    status: "Complete",
    detail: "Complete",
    icon: CheckCircle2,
    tone: "border-emerald-100 bg-emerald-50 text-emerald-600",
    badgeVariant: "success" as BadgeVariant,
  },
  {
    title: "Test Design",
    status: "Pending Review",
    detail: "Approval required",
    icon: ClipboardCheck,
    tone: "border-amber-100 bg-amber-50 text-amber-600",
    badgeVariant: "warning" as BadgeVariant,
  },
  {
    title: "Application Discovery",
    status: "Ready",
    detail: "Ready",
    icon: Search,
    tone: "border-emerald-100 bg-emerald-50 text-emerald-600",
    badgeVariant: "success" as BadgeVariant,
  },
  {
    title: "Automation Studio",
    status: "In Progress",
    detail: "IR validated",
    icon: Sparkles,
    tone: "border-blue-100 bg-blue-50 text-[#1b59f8]",
    badgeVariant: "info" as BadgeVariant,
  },
  {
    title: "Execution",
    status: "In Progress",
    detail: "12 active runs",
    icon: Play,
    tone: "border-violet-100 bg-violet-50 text-violet-600",
    badgeVariant: "purple" as BadgeVariant,
  },
  {
    title: "Evidence & Review",
    status: "In Progress",
    detail: "85% quorum met",
    icon: Shield,
    tone: "border-blue-100 bg-blue-50 text-[#1b59f8]",
    badgeVariant: "info" as BadgeVariant,
  },
];

const activity = [
  ["Requirement REQ-0012 approved", "01:10 PM", "Surya", "success"],
  ["Test Cases for REQ-0012 pending review", "12:58 PM", "AI Agent (QA Gen)", "warning"],
  ["Automation IR validated for CRM Portal", "12:45 PM", "Surya", "info"],
  ["Execution run RUN-0456 started on AVD-03", "12:30 PM", "System", "purple"],
  ["Evidence uploaded for RUN-0455", "12:10 PM", "AI Agent (Evidence)", "outline"],
] as const;

function MetricCard({ item }: { item: (typeof metrics)[number] }) {
  const Icon = item.icon;

  return (
    <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-sm">
      <CardContent className="p-4">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${item.tone}`}>
            <Icon className="h-5 w-5" />
          </div>
          <Badge variant={item.badgeVariant} className="whitespace-nowrap text-[10px]">
            {item.badge}
          </Badge>
        </div>
        <p className="text-sm font-semibold text-slate-900">{item.title}</p>
        <div className="mt-5 flex items-end gap-2">
          <span className="text-3xl font-bold tracking-tight text-slate-950">{item.value}</span>
          <span className="pb-1 text-xs text-slate-500">{item.suffix}</span>
        </div>
        <p className="mt-3 text-xs text-slate-500">{item.note}</p>
      </CardContent>
    </Card>
  );
}

function LifecycleStep({ item, index, last }: { item: (typeof lifecycle)[number]; index: number; last?: boolean }) {
  const Icon = item.icon;

  return (
    <div className="flex min-w-0 flex-1 items-center">
      <div className="flex min-w-[150px] items-center gap-3">
        <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full border ${item.tone}`}>
          <Icon className="h-6 w-6" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold leading-5 text-slate-950">{index}. {item.title}</p>
          <Badge variant={item.badgeVariant} className="mt-1 text-[10px]">{item.status}</Badge>
          <p className="mt-1 text-xs text-slate-500">{item.detail}</p>
        </div>
      </div>
      {!last && <div className="mx-4 hidden h-px min-w-8 flex-1 bg-slate-300 xl:block" />}
    </div>
  );
}

function ReadinessRow({
  icon: Icon,
  label,
  value,
  warning = false,
}: {
  icon: typeof CheckCircle2;
  label: string;
  value: string;
  warning?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-3">
        <Icon className={`h-4 w-4 shrink-0 ${warning ? "text-amber-500" : "text-emerald-500"}`} />
        <span className="truncate text-slate-700">{label}</span>
      </div>
      <span className={`shrink-0 text-xs font-medium ${warning ? "text-amber-600" : "text-emerald-600"}`}>{value}</span>
    </div>
  );
}

function QueueRow({
  icon: Icon,
  label,
  count,
  variant,
}: {
  icon: typeof Bell;
  label: string;
  count: number;
  variant: BadgeVariant;
}) {
  const iconColor = variant === "warning" ? "text-amber-500" : variant === "destructive" ? "text-red-500" : "text-blue-500";

  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-3">
        <Icon className={`h-4 w-4 shrink-0 ${iconColor}`} />
        <span className="truncate text-slate-700">{label}</span>
      </div>
      <Badge variant={variant} className="min-w-6 justify-center px-2 text-[10px]">{count}</Badge>
    </div>
  );
}

function EvidenceRing() {
  return (
    <div className="relative h-36 w-36 shrink-0">
      <svg className="h-36 w-36 -rotate-90" viewBox="0 0 100 100" aria-label="Evidence quorum is 85 percent">
        <circle cx="50" cy="50" r="38" fill="none" stroke="#e2e8f0" strokeWidth="10" />
        <circle cx="50" cy="50" r="38" fill="none" stroke="#34d399" strokeWidth="10" strokeLinecap="round" strokeDasharray="204 239" />
        <circle cx="50" cy="50" r="38" fill="none" stroke="#fbbf24" strokeWidth="10" strokeLinecap="round" strokeDasharray="38 239" strokeDashoffset="-150" />
        <circle cx="50" cy="50" r="38" fill="none" stroke="#ef4444" strokeWidth="10" strokeLinecap="round" strokeDasharray="19 239" strokeDashoffset="-188" />
        <circle cx="50" cy="50" r="38" fill="none" stroke="#8b5cf6" strokeWidth="10" strokeLinecap="round" strokeDasharray="17 239" strokeDashoffset="-214" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-slate-950">85%</span>
        <span className="text-xs text-slate-500">Quorum Met</span>
      </div>
    </div>
  );
}

function ActionRow({ label, href, button }: { label: string; href: string; button: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 text-sm">
      <span className="text-slate-700">{label}</span>
      <Button asChild variant="outline" size="sm" className="border-violet-300 text-violet-700 hover:bg-violet-50">
        <Link href={href}>{button}</Link>
      </Button>
    </div>
  );
}

export default function ExecutiveOverviewPage() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-1 pb-4">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>e&amp; STLC</span>
          <ChevronRight className="h-3 w-3" />
          <span className="font-medium text-[#1b59f8]">Command Centre</span>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-slate-400">
            Project
            <select className="h-9 min-w-[220px] rounded-lg border border-slate-200 bg-white px-3 text-sm normal-case tracking-normal text-slate-900">
              <option>Testing 47</option>
            </select>
          </label>
          <Badge variant="success" className="gap-1">
            <CheckCircle2 className="h-3 w-3" /> Jira Synced just now
          </Badge>
        </div>
      </div>

      <section className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-[#1b59f8]">
            <FileText className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-950">Executive Overview</h1>
            <p className="mt-1 text-sm text-slate-500">
              Command centre for AAF lifecycle across requirements, design, discovery, automation, execution and evidence.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <label className="flex items-center gap-2">
            Environment:
            <select className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900">
              <option>QA (AVD)</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            Release / Cycle:
            <select className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900">
              <option>Q3 Release</option>
            </select>
          </label>
          <span>Last refreshed: Jul 21, 2026 01:15 PM</span>
          <Button variant="outline" size="icon" aria-label="Refresh Command Centre">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        {metrics.map((metric) => <MetricCard key={metric.title} item={metric} />)}
      </section>

      <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-sm">
        <CardContent className="p-6">
          <h2 className="mb-6 text-sm font-semibold text-slate-950">AAF Lifecycle - Phase 1 Operating Domains</h2>
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center">
            {lifecycle.map((item, index) => (
              <LifecycleStep key={item.title} item={item} index={index + 1} last={index === lifecycle.length - 1} />
            ))}
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Readiness &amp; Blockers</h2>
            <ReadinessRow icon={CheckCircle2} label="Environment Readiness" value="Healthy" />
            <ReadinessRow icon={CheckCircle2} label="Discovery & App Model" value="Ready" />
            <ReadinessRow icon={TriangleAlert} label="Automation IR & Validation" value="IR Validated (64%)" warning />
            <ReadinessRow icon={CheckCircle2} label="Mandatory Evidence Policy" value="Compliant" />
            <ReadinessRow icon={CheckCircle2} label="Agent Governance" value="Compliant" />
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href="/autonomous-lab/missions">
              View all gates <ChevronRight className="ml-1 h-4 w-4" />
            </Link>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Work Queue</h2>
            <QueueRow icon={Bell} label="Approvals Waiting on You" count={3} variant="warning" />
            <QueueRow icon={Bot} label="Agent Handoffs" count={2} variant="warning" />
            <QueueRow icon={PauseCircle} label="Paused Work Items" count={1} variant="outline" />
            <QueueRow icon={XCircle} label="Failed Jobs" count={0} variant="outline" />
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href="/autonomous-lab/missions">
              Go to Work Queue <ChevronRight className="ml-1 h-4 w-4" />
            </Link>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Risk &amp; Evidence Summary</h2>
            <div className="flex flex-col items-center gap-5 sm:flex-row">
              <EvidenceRing />
              <div className="w-full space-y-3 text-sm">
                <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-slate-600"><span className="h-2 w-2 rounded-full bg-emerald-400" />Pass</span><span className="text-slate-500">62% (26)</span></div>
                <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-slate-600"><span className="h-2 w-2 rounded-full bg-amber-400" />Inconclusive</span><span className="text-slate-500">23% (10)</span></div>
                <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-slate-600"><span className="h-2 w-2 rounded-full bg-red-400" />Fail</span><span className="text-slate-500">8% (3)</span></div>
                <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-slate-600"><span className="h-2 w-2 rounded-full bg-slate-300" />Missing Evidence</span><span className="text-slate-500">7% (3)</span></div>
              </div>
            </div>
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href="/autonomous-lab/missions">
              Open Evidence Dashboard <ChevronRight className="ml-1 h-4 w-4" />
            </Link>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Recent Activity</h2>
            <div className="divide-y divide-slate-100">
              {activity.map(([label, time, actor, variant]) => (
                <div key={label} className="grid grid-cols-[1fr_auto_auto] items-center gap-4 py-3 text-sm">
                  <span className="min-w-0 truncate text-slate-700">{label}</span>
                  <span className="text-xs text-slate-500">{time}</span>
                  <Badge variant={variant as BadgeVariant} className="text-[10px]">{actor}</Badge>
                </div>
              ))}
            </div>
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href="/autonomous-lab/missions">
              View full timeline <ChevronRight className="ml-1 h-4 w-4" />
            </Link>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Next Actions</h2>
            <div className="divide-y divide-slate-100">
              <ActionRow label="Review & approve pending test cases" href="/test-cases" button="Open Test Cases" />
              <ActionRow label="Complete automation for low readiness items" href="/automation" button="Open Automation" />
              <ActionRow label="Monitor running executions" href="/execution" button="Live Execution" />
              <ActionRow label="Review evidence gaps" href="/reports" button="View Evidence" />
              <ActionRow label="Review pending approvals" href="/requirements" button="Open Approvals" />
            </div>
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs text-blue-800">
              <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Actions are permission and gate aware in the full AAF service integration.
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
