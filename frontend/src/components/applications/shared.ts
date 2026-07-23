import type { ProjectApplication } from "@/lib/api";

export type QueueTab = "all" | "active" | "draft" | "needs_review" | "discovery_ready" | "health_issues" | "deprecated_retired";
export type Tone = "blue" | "emerald" | "red" | "purple" | "amber" | "slate";

export function messageFromError(error: unknown, fallback: string): string {
  const candidate = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = candidate?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return candidate?.message || fallback;
}

export function resolveUserName(names: Map<number, string>, id?: number | null): string {
  if (!id) return "—";
  return names.get(id) || `User #${id}`;
}

export function applicationHasEnvironment(app: ProjectApplication): boolean {
  return Object.keys(app.environment_urls || {}).length > 0;
}

export function applicationHasProductMapping(app: ProjectApplication): boolean {
  return Boolean(app.product_group || app.product || app.channel);
}

// A "gap" is a real, persisted-field absence — never a fabricated readiness
// signal. Used both for the Needs Review queue bucket and the inspector's
// honest "missing metadata" list (contract: missing metadata must be shown
// as missing, not invented).
export function applicationGaps(app: ProjectApplication): string[] {
  const gaps: string[] = [];
  if (!app.business_owner_id && !app.technical_owner_id) gaps.push("No owner assigned.");
  if (!applicationHasEnvironment(app)) gaps.push("No environment configured.");
  if (!applicationHasProductMapping(app)) gaps.push("No domain, product or channel mapped.");
  return gaps;
}

export function getQueueTab(app: ProjectApplication): Exclude<QueueTab, "all" | "health_issues"> | "other" {
  if (app.lifecycle_status === "deprecated" || app.lifecycle_status === "retired") return "deprecated_retired";
  if (app.lifecycle_status === "draft" && applicationGaps(app).length > 0) return "needs_review";
  if (app.lifecycle_status === "draft") return "draft";
  if (app.is_active && applicationHasEnvironment(app)) return "discovery_ready";
  if (app.is_active) return "active";
  return "other";
}

export function badgeVariant(tone: Tone): "success" | "warning" | "destructive" | "purple" | "info" | "secondary" {
  const map: Record<Tone, "success" | "warning" | "destructive" | "purple" | "info" | "secondary"> = {
    blue: "info", emerald: "success", red: "destructive", purple: "purple", amber: "warning", slate: "secondary",
  };
  return map[tone];
}

export function lifecycleBadgeTone(status: ProjectApplication["lifecycle_status"]): Tone {
  if (status === "active") return "emerald";
  if (status === "draft") return "slate";
  if (status === "deprecated") return "amber";
  return "red"; // retired
}
