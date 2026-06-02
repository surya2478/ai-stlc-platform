"use client";

import { Bell, Plus, Search, User } from "lucide-react";
import Link from "next/link";

export function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-6">
      {/* Search */}
      <div className="flex items-center gap-2 rounded-md border bg-background px-3 py-1.5 text-sm text-muted-foreground w-64">
        <Search className="h-3.5 w-3.5" />
        <span>Search projects, tests…</span>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-3">
        <Link
          href="/projects/new"
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New Project
        </Link>

        <button className="relative rounded-md p-1.5 hover:bg-accent transition-colors">
          <Bell className="h-4 w-4 text-muted-foreground" />
          {/* Notification dot */}
          <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-red-500" />
        </button>

        <button className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold">
          <User className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
