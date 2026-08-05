"use client";

/**
 * Phase 3: /execution/ai is retired.
 *
 * AI is now a mode of automation execution, not a separate menu. Any existing
 * bookmarks or deep links land here and get forwarded to the AI-Assisted view
 * inside Automation Execution. The query string (project, env, etc.) is
 * preserved so the destination reopens in the same context.
 */

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, Sparkles } from "lucide-react";
import Link from "next/link";

function Redirector() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const next = new URLSearchParams(params.toString());
    next.set("mode", "ai-assisted");
    router.replace(`/execution/automation?${next.toString()}`);
  }, [router, params]);

  return (
    <div className="flex h-full min-h-[400px] flex-col items-center justify-center gap-3 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-violet-50">
        <Sparkles className="h-5 w-5 text-violet-600" />
      </div>
      <p className="text-sm font-semibold text-gray-800">AI Execution has moved</p>
      <p className="max-w-sm text-xs text-gray-500">
        AI is now a mode of Automation Execution. Taking you to the AI-Assisted view now…
      </p>
      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-gray-400">
        <Loader2 className="h-3 w-3 animate-spin" />
        Redirecting
      </div>
      <Link
        href="/execution/automation?mode=ai-assisted"
        className="mt-2 text-[11px] text-violet-600 hover:underline"
      >
        Click here if you are not redirected automatically
      </Link>
    </div>
  );
}

export default function AiExecutionRedirectPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-gray-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#B71920] mr-2" />
        Loading…
      </div>
    }>
      <Redirector />
    </Suspense>
  );
}
