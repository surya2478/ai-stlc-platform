"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

// Suggestions only — ExecutionRun.environment is free text (it also carries
// real deployment-target names like "QA-Staging" from Project Applications),
// so this stays a text input with a datalist rather than a closed <select>.
const ENV_SUGGESTIONS = ["SIT", "QA", "UAT", "Regression", "Production Smoke Test"];

/** Local "Environment" filter for the Execution pages — sets the `?env=` query
 * param that ExecutionDashboard/Manual/Automation already read to filter runs
 * and (on Manual/Automation) to tag newly started runs. Scoped to these pages
 * only (previously a global Header dropdown that wasn't wired to anything
 * outside Execution). */
export function EnvironmentFilter({ defaultValue = "" }: { defaultValue?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlEnv = searchParams.get("env") ?? defaultValue;
  const [draft, setDraft] = useState(urlEnv);

  useEffect(() => setDraft(urlEnv), [urlEnv]);

  const commit = (val: string) => {
    if (val === urlEnv) return;
    const params = new URLSearchParams(searchParams.toString());
    if (val) {
      params.set("env", val);
    } else {
      params.delete("env");
    }
    router.push(`${pathname}?${params.toString()}`);
  };

  return (
    <div className="hidden md:flex shrink-0 items-center gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
        Environment
      </span>
      <input
        list="environment-filter-suggestions"
        value={draft}
        placeholder="All"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={(e) => commit(e.target.value.trim())}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit((e.target as HTMLInputElement).value.trim());
        }}
        className="w-32 bg-gray-50 hover:bg-gray-100 border border-gray-200 text-gray-800 rounded-lg text-xs font-medium px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#B71920] transition-colors"
      />
      <datalist id="environment-filter-suggestions">
        {ENV_SUGGESTIONS.map((env) => (
          <option key={env} value={env} />
        ))}
      </datalist>
    </div>
  );
}
