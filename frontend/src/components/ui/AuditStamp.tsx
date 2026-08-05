import * as React from "react";
import { cn } from "@/lib/utils";
import { Clock, User } from "lucide-react";

export interface AuditStampProps extends React.HTMLAttributes<HTMLDivElement> {
  createdAt?: string | Date;
  updatedAt?: string | Date;
  createdByName?: string;
  updatedByName?: string;
  compact?: boolean;
}

export function AuditStamp({
  createdAt,
  updatedAt,
  createdByName,
  updatedByName,
  compact = false,
  className,
  ...props
}: AuditStampProps) {
  const formatDateTime = (dateStr?: string | Date) => {
    if (!dateStr) return null;
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return null;
      return d.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return null;
    }
  };

  const formattedCreated = formatDateTime(createdAt);
  const formattedUpdated = formatDateTime(updatedAt);

  // If there's no audit info at all, render nothing or a clean dash
  if (!formattedCreated && !formattedUpdated) {
    return <span className="text-gray-400">—</span>;
  }

  // Show "Modified" only if it's actually different from "Created" (within 1 min margin of error) or if no created date is provided but updated is.
  const hasModified = (() => {
    if (!formattedUpdated) return false;
    if (!formattedCreated) return true;
    const cTime = new Date(createdAt!).getTime();
    const uTime = new Date(updatedAt!).getTime();
    // More than 10 seconds difference
    return Math.abs(uTime - cTime) > 10000;
  })();

  if (compact) {
    return (
      <div
        className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-gray-500", className)}
        {...props}
      >
        {formattedCreated && (
          <div className="flex items-center gap-1" title={`Created at: ${new Date(createdAt!).toISOString()}`}>
            <span className="font-semibold text-gray-700">Created:</span>
            <span>{formattedCreated}</span>
            {createdByName && (
              <span className="font-medium text-gray-600">by {createdByName}</span>
            )}
          </div>
        )}
        {hasModified && formattedUpdated && (
          <>
            <span className="text-gray-300">·</span>
            <div className="flex items-center gap-1" title={`Modified at: ${new Date(updatedAt!).toISOString()}`}>
              <span className="font-semibold text-gray-700">Modified:</span>
              <span>{formattedUpdated}</span>
              {updatedByName && (
                <span className="font-medium text-gray-600">by {updatedByName}</span>
              )}
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn("space-y-1.5 text-xs text-gray-500 bg-gray-50/50 p-2.5 rounded-lg border border-gray-100/80", className)}
      {...props}
    >
      {formattedCreated && (
        <div
          className="flex items-center justify-between gap-4"
          title={`Created: ${new Date(createdAt!).toISOString()}`}
        >
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-gray-400" />
            <span className="font-medium text-gray-700">Created</span>
          </div>
          <div className="flex items-center gap-2 text-right">
            <span>{formattedCreated}</span>
            {createdByName && (
              <span className="flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 font-medium">
                <User className="w-3 h-3 text-gray-400" />
                {createdByName}
              </span>
            )}
          </div>
        </div>
      )}
      {hasModified && formattedUpdated && (
        <div
          className="flex items-center justify-between gap-4 pt-1.5 border-t border-gray-100"
          title={`Modified: ${new Date(updatedAt!).toISOString()}`}
        >
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-gray-400" />
            <span className="font-medium text-gray-700">Modified</span>
          </div>
          <div className="flex items-center gap-2 text-right">
            <span>{formattedUpdated}</span>
            {updatedByName && (
              <span className="flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 font-medium">
                <User className="w-3 h-3 text-gray-400" />
                {updatedByName}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
