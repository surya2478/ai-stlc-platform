import { Sidebar } from "@/components/layout/Sidebar";

export default function AutonomousLabLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden p-6">{children}</main>
    </div>
  );
}
