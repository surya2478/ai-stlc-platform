import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  color: string;
  bg: string;
  trend?: string;
}

export function StatCard({ label, value, icon: Icon, color, bg, trend }: StatCardProps) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div className={cn("rounded-lg p-2", bg)}>
          <Icon className={cn("h-4 w-4", color)} />
        </div>
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
      </div>
      {trend && (
        <p className="mt-2 text-xs text-green-600 dark:text-green-400">{trend}</p>
      )}
    </div>
  );
}
