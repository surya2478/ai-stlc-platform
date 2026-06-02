"use client";

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";

const PLACEHOLDER_DATA = [
  { date: "Mon", passed: 0, failed: 0, skipped: 0 },
  { date: "Tue", passed: 0, failed: 0, skipped: 0 },
  { date: "Wed", passed: 0, failed: 0, skipped: 0 },
  { date: "Thu", passed: 0, failed: 0, skipped: 0 },
  { date: "Fri", passed: 0, failed: 0, skipped: 0 },
  { date: "Sat", passed: 0, failed: 0, skipped: 0 },
  { date: "Sun", passed: 0, failed: 0, skipped: 0 },
];

export function ExecutionTrendChart() {
  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <h3 className="font-semibold text-sm mb-4">Execution Trend (Last 7 Days)</h3>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={PLACEHOLDER_DATA} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="passed" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="failed" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{ fontSize: "12px", borderRadius: "8px" }}
          />
          <Legend wrapperStyle={{ fontSize: "12px" }} />
          <Area type="monotone" dataKey="passed" stroke="#22c55e" fill="url(#passed)" strokeWidth={2} />
          <Area type="monotone" dataKey="failed" stroke="#ef4444" fill="url(#failed)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
      <p className="text-xs text-muted-foreground text-center mt-2">
        No execution data yet — run your first test suite to see trends.
      </p>
    </div>
  );
}
