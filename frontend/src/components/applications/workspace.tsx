"use client";

/**
 * The shared shell the four Applications screens are built from.
 *
 * UI-015/016/017 each grew their own miniature design system — 9px labels, a
 * three-column panel grid, an inspector hidden behind a `<select>`, and
 * `window.prompt()` for anything that needed a reason. The result was three
 * screens that looked nothing like the Test Case module they sit beside and
 * gave no answer to "what am I supposed to do here?".
 *
 * These are the Test Case module's primitives, extracted so all three screens
 * are literally the same components rather than three approximations of them:
 * a summary strip, a filter bar, a selectable list, and a tabbed drawer with
 * guidance and validation. Sizes match Test Cases exactly (text-xs body,
 * text-[10px] labels, h-9 controls) — nothing smaller.
 */

import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, Info, Loader2, Lock, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";
import type { Tone } from "./shared";

const TONE_TILE: Record<Tone, string> = {
  blue: "bg-blue-50 border-blue-100 text-blue-600",
  emerald: "bg-emerald-50 border-emerald-100 text-emerald-600",
  red: "bg-red-50 border-red-100 text-red-600",
  purple: "bg-purple-50 border-purple-100 text-purple-600",
  amber: "bg-amber-50 border-amber-100 text-amber-600",
  slate: "bg-slate-50 border-slate-100 text-slate-600",
};

const TONE_TEXT: Record<Tone, string> = {
  blue: "text-blue-700",
  emerald: "text-emerald-700",
  red: "text-red-700",
  purple: "text-purple-700",
  amber: "text-amber-700",
  slate: "text-slate-700",
};

/* ── page chrome ─────────────────────────────────────────────────────── */

export function Breadcrumb({ trail }: { trail: string[] }) {
  return (
    <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
      {trail.map((item, index) => (
        <span key={item} className="flex items-center gap-2">
          {index > 0 && <ChevronRight className="h-3 w-3 text-slate-300" />}
          <span className={index === trail.length - 1 ? "text-[#1b59f8]" : undefined}>{item}</span>
        </span>
      ))}
    </div>
  );
}

export function WorkspaceHeader({
  icon: Icon,
  tone,
  title,
  badge,
  description,
  actions,
}: {
  icon: typeof Info;
  tone: Tone;
  title: string;
  badge: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <div className={cn("mt-1 flex h-9 w-9 items-center justify-center rounded-lg border", TONE_TILE[tone])}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-950">{title}</h1>
            <Badge variant="purple">{badge}</Badge>
          </div>
          <p className="mt-1 text-xs font-semibold text-slate-500">{description}</p>
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  title, value, subtitle, icon: Icon, tone,
}: {
  title: string; value: string | number; subtitle: string; icon: typeof Info; tone: Tone;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2.5">
        <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", TONE_TILE[tone])}>
          <Icon className="h-4 w-4" />
        </div>
        <p className="min-w-0 truncate text-xs font-bold text-slate-700">{title}</p>
      </div>
      <p className="mt-3 text-2xl font-extrabold leading-none text-slate-950">{value}</p>
      <p className="mt-1.5 text-[11px] font-semibold text-slate-500">{subtitle}</p>
    </div>
  );
}

/**
 * The one thing every one of these screens was missing: a plain sentence
 * saying what to do next, and the button that does it.
 *
 * `blocked` states must always carry a `detail` explaining what is in the way
 * — a disabled control with no reason is the exact failure this replaces.
 */
export function GuidanceCard({
  tone = "blue",
  title,
  detail,
  action,
  secondary,
}: {
  tone?: "blue" | "amber" | "emerald" | "red";
  title: string;
  detail: string;
  action?: ReactNode;
  secondary?: ReactNode;
}) {
  const skin = {
    blue: "border-blue-200 bg-blue-50/60 text-blue-900",
    amber: "border-amber-200 bg-amber-50/60 text-amber-900",
    emerald: "border-emerald-200 bg-emerald-50/60 text-emerald-900",
    red: "border-red-200 bg-red-50/60 text-red-900",
  }[tone];
  const Icon = tone === "amber" || tone === "red" ? AlertTriangle : tone === "emerald" ? CheckCircle2 : Info;
  const iconColor = {
    blue: "text-blue-600", amber: "text-amber-600", emerald: "text-emerald-600", red: "text-red-600",
  }[tone];

  return (
    <div className={cn("flex flex-wrap items-center gap-3 rounded-lg border p-4 shadow-sm", skin)}>
      <Icon className={cn("h-4 w-4 shrink-0", iconColor)} />
      <div className="min-w-[18rem] flex-1">
        <p className="text-xs font-extrabold">{title}</p>
        <p className="mt-0.5 text-[11px] font-semibold opacity-80">{detail}</p>
      </div>
      {secondary}
      {action}
    </div>
  );
}

export function Notices({
  error, notice, onDismiss,
}: {
  error: string; notice: string; onDismiss: () => void;
}) {
  if (!error && !notice) return null;
  return (
    <div className={cn(
      "flex items-center gap-2 rounded-lg border px-4 py-3 text-xs font-semibold",
      error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700",
    )}>
      {error ? <AlertTriangle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span className="flex-1">{error || notice}</span>
      <button onClick={onDismiss} aria-label="Dismiss" className="text-current/60 hover:text-current">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

/* ── filtering + list ────────────────────────────────────────────────── */

export function QueueTabs<T extends string>({
  tabs, active, counts, onChange,
}: {
  tabs: { key: T; label: string }[];
  active: T;
  counts: Record<string, number>;
  onChange: (key: T) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-lg bg-slate-50 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-bold transition",
            active === tab.key ? "bg-[#07142d] text-white" : "text-slate-600 hover:bg-white",
          )}
        >
          {tab.label}
          <span className={cn(
            "rounded-full px-1.5 py-0.5 text-[10px]",
            active === tab.key ? "bg-white/15 text-white" : "bg-slate-200 text-slate-500",
          )}>
            {counts[tab.key] ?? 0}
          </span>
        </button>
      ))}
    </div>
  );
}

export function FilterSelect({
  value, onChange, options, label,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  label: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
      className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
    >
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  );
}

export function ListShell({
  columns, gridTemplate, loading, empty, footer, children, minWidth = 1100,
}: {
  columns: string[];
  gridTemplate: string;
  loading?: boolean;
  empty?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  minWidth?: number;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <div
        className="grid border-b border-slate-200 bg-slate-50/70 px-3 py-2.5 text-[10px] font-extrabold uppercase tracking-wide text-slate-500"
        style={{ gridTemplateColumns: gridTemplate, minWidth }}
      >
        {columns.map((column) => <span key={column}>{column}</span>)}
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-16 text-xs font-bold text-slate-500">
          <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" /> Loading…
        </div>
      ) : empty ? (
        <div className="px-6 py-16 text-center">{empty}</div>
      ) : (
        <div className="divide-y divide-slate-100" style={{ minWidth }}>{children}</div>
      )}
      {footer && <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2.5">{footer}</div>}
    </div>
  );
}

export function ListRow({
  gridTemplate, selected, onClick, children,
}: {
  gridTemplate: string;
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{ gridTemplateColumns: gridTemplate }}
      className={cn(
        "grid w-full items-center gap-2 px-3 py-2.5 text-left text-[11px] transition hover:bg-slate-50",
        selected && "border-l-2 border-[#1b59f8] bg-blue-50/30",
      )}
    >
      {children}
    </button>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="mx-auto max-w-md">
      <p className="text-sm font-bold text-slate-700">{title}</p>
      <p className="mt-1.5 text-xs font-semibold leading-5 text-slate-500">{detail}</p>
      {action && <div className="mt-4 flex justify-center gap-2">{action}</div>}
    </div>
  );
}

/* ── drawer building blocks ──────────────────────────────────────────── */

export type DrawerTabSpec<T extends string> = {
  key: T;
  label: string;
  /** Unavailable tabs stay visible and locked with a reason, never hidden. */
  available?: boolean;
  reason?: string;
};

export function DrawerTabBar<T extends string>({
  tabs, active, onChange,
}: {
  tabs: DrawerTabSpec<T>[];
  active: T;
  onChange: (key: T) => void;
}) {
  return (
    <div className="flex flex-wrap border-b border-slate-100 px-4">
      {tabs.map((tab) => {
        const available = tab.available !== false;
        return (
          <button
            key={tab.key}
            disabled={!available}
            title={available ? undefined : tab.reason}
            onClick={() => available && onChange(tab.key)}
            className={cn(
              "flex items-center gap-1 border-b-2 px-3 py-3 text-xs font-bold transition",
              !available && "cursor-not-allowed border-transparent text-slate-300",
              available && active === tab.key && "border-[#1b59f8] text-[#1b59f8]",
              available && active !== tab.key && "border-transparent text-slate-600 hover:text-slate-900",
            )}
          >
            {!available && <Lock className="h-2.5 w-2.5" />}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export function DrawerCard({
  title, icon: Icon, action, children,
}: {
  title: string;
  icon?: typeof Info;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-3.5 w-3.5 text-slate-400" />}
          <h4 className="text-xs font-extrabold text-slate-800">{title}</h4>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function InfoPair({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-extrabold uppercase tracking-wide text-slate-400">{label}</p>
      <p className={cn("mt-1 break-words text-xs font-bold text-slate-800", mono && "font-mono")}>{value ?? "—"}</p>
    </div>
  );
}

export function ChecklistRow({
  label, state, detail,
}: {
  label: string;
  state: "pass" | "warning" | "blocked" | "not_evaluated";
  detail: string;
}) {
  const icon = state === "pass" ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    : state === "warning" ? <AlertTriangle className="h-4 w-4 text-amber-500" />
    : state === "blocked" ? <X className="h-4 w-4 text-red-500" />
    : <Info className="h-4 w-4 text-slate-300" />;
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs font-bold text-slate-800">{label}</p>
        <p className="mt-0.5 text-[11px] font-semibold leading-4 text-slate-500">{detail}</p>
      </div>
    </div>
  );
}

export function ToneValue({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={cn("font-extrabold", TONE_TEXT[tone])}>{children}</span>;
}

/* ── reason capture ──────────────────────────────────────────────────── */

/**
 * Replaces `window.prompt()`, which every governed action on these screens
 * used to collect its audit reason. A browser prompt cannot explain what the
 * reason is for, cannot enforce a minimum, cannot be cancelled safely on a
 * misclick, and is unstyled — for text that is written to an immutable audit
 * trail, that was the wrong control.
 */
export function ReasonDrawer({
  open, title, description, label, placeholder, confirmLabel, destructive, required = true,
  minLength = 5, busy, onCancel, onConfirm,
}: {
  open: boolean;
  title: string;
  description: string;
  label: string;
  placeholder: string;
  confirmLabel: string;
  destructive?: boolean;
  required?: boolean;
  minLength?: number;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (open) { setReason(""); setTouched(false); }
  }, [open]);

  const trimmed = reason.trim();
  const error = !required && !trimmed
    ? ""
    : !trimmed
      ? `${label} is required — it is written to the audit trail.`
      : trimmed.length < minLength
        ? `Give at least ${minLength} characters so the trail explains itself later.`
        : "";
  const showError = touched && Boolean(error);

  return (
    <Drawer open={open} onOpenChange={(next) => !next && !busy && onCancel()}>
      <DrawerContent size="lg">
        <DrawerHeader>
          <div>
            <DrawerTitle>{title}</DrawerTitle>
            <DrawerDescription>{description}</DrawerDescription>
          </div>
          <button aria-label="Close" onClick={() => !busy && onCancel()} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50">
            <X className="h-4 w-4" />
          </button>
        </DrawerHeader>
        <DrawerBody>
          <label className="block">
            <span className="mb-1 block text-[10px] font-extrabold uppercase tracking-wide text-slate-500">
              {label} {required ? "*" : <span className="font-bold normal-case text-slate-400">(optional)</span>}
            </span>
            <textarea
              autoFocus
              value={reason}
              onChange={(e) => { setReason(e.target.value); setTouched(true); }}
              onBlur={() => setTouched(true)}
              rows={5}
              placeholder={placeholder}
              className={cn(
                "w-full rounded-lg border px-3 py-2 text-xs font-semibold outline-none focus:ring-2",
                showError ? "border-red-300 focus:ring-red-100" : "border-slate-200 focus:ring-blue-100",
              )}
            />
          </label>
          {showError ? (
            <p className="flex items-center gap-1.5 text-[11px] font-bold text-red-700">
              <AlertTriangle className="h-3.5 w-3.5" />{error}
            </p>
          ) : (
            <p className="text-[11px] font-semibold text-slate-400">
              This is recorded against your user and cannot be edited afterwards.
            </p>
          )}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="outline" size="sm" disabled={busy} onClick={onCancel}>Cancel</Button>
          <Button
            size="sm"
            variant={destructive ? "destructive" : "default"}
            disabled={busy || Boolean(error)}
            onClick={() => onConfirm(trimmed)}
          >
            {busy && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {confirmLabel}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

/** Config for a pending reason-gated action, held while the drawer is open. */
export type ReasonRequest = {
  title: string;
  description: string;
  label: string;
  placeholder: string;
  confirmLabel: string;
  destructive?: boolean;
  required?: boolean;
  minLength?: number;
  onConfirm: (reason: string) => void | Promise<void>;
};
