"use client";

import { useState } from "react";
import { Loader2, Plug, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import type { McpConnection } from "@/lib/api";
import {
  useCreateMcpConnection,
  useDeleteMcpConnection,
  useMcpConnections,
  useTestAllMcpConnections,
  useTestMcpConnection,
} from "@/lib/queries/playwrightStudio";

const TYPE_LABEL: Record<string, string> = {
  browser: "Browser MCP",
  api: "REST API MCP",
  db: "Database MCP",
  kafka: "Kafka MCP",
  application: "Application MCP",
  custom: "Custom MCP",
};

const AGENT_CHIPS: Array<{ key: string; label: string }> = [
  { key: "planner", label: "P" },
  { key: "generator", label: "G" },
  { key: "execution", label: "E" },
  { key: "healer", label: "H" },
];

function statusVariant(status: string): "success" | "warning" | "destructive" | "outline" {
  if (status === "connected") return "success";
  if (status === "error") return "destructive";
  return "warning";
}

function statusLabel(status: string): string {
  if (status === "connected") return "Connected";
  if (status === "error") return "Error";
  return "Not Configured";
}

/** MCP Connections & Validation panel (Studio Step 1). v1 = registry +
 * health checks: agents don't call external MCPs during runs yet; the
 * built-in Playwright Browser MCP is the live one. */
export function McpConnectionsPanel({ projectId }: { projectId: number | null }) {
  const { toast } = useToast();
  const { data: connections = [], isLoading } = useMcpConnections(projectId);
  const createConnection = useCreateMcpConnection(projectId);
  const deleteConnection = useDeleteMcpConnection(projectId);
  const testConnection = useTestMcpConnection(projectId);
  const testAll = useTestAllMcpConnections(projectId);

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    name: "",
    connection_type: "api",
    transport: "stdio",
    target: "",
    command: "npx",
    argsText: "",
    url: "",
    envText: "",
    access_mode: "read_only",
  });
  const [testingId, setTestingId] = useState<number | null>(null);

  const connected = connections.filter((c) => c.status === "connected").length;

  async function handleAdd() {
    if (!projectId || !form.name.trim()) return;
    let env: Record<string, string> | undefined;
    if (form.envText.trim()) {
      env = {};
      for (const line of form.envText.split("\n")) {
        const idx = line.indexOf("=");
        if (idx > 0) env[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
      }
    }
    try {
      await createConnection.mutateAsync({
        project_id: projectId,
        name: form.name.trim(),
        connection_type: form.connection_type,
        transport: form.transport,
        target: form.target.trim() || undefined,
        command: form.transport === "stdio" ? form.command.trim() : undefined,
        args: form.transport === "stdio" && form.argsText.trim()
          ? form.argsText.trim().split(/\s+/)
          : undefined,
        url: form.transport === "http" ? form.url.trim() : undefined,
        env,
        access_mode: form.access_mode,
        available_to: ["planner", "generator", "execution", "healer"],
      });
      setShowAdd(false);
      setForm({ ...form, name: "", target: "", argsText: "", url: "", envText: "" });
      toast({ title: "MCP connection added", description: "Run Test Connection to verify it." });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: "Could not add connection", description: detail ?? "Unknown error", variant: "error" });
    }
  }

  async function handleTest(connection: McpConnection) {
    setTestingId(connection.id);
    try {
      const updated = await testConnection.mutateAsync(connection.id);
      toast({
        title: updated.status === "connected" ? "Connected" : "Connection failed",
        description:
          updated.status === "connected"
            ? `${updated.name}: ${updated.tool_count ?? 0} tool(s) available`
            : updated.last_error ?? "Unknown error",
        variant: updated.status === "connected" ? "success" : "error",
      });
    } finally {
      setTestingId(null);
    }
  }

  const inputClass =
    "w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500";

  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/40 p-4 dark:border-violet-900 dark:bg-violet-950/20">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Plug className="h-4 w-4 text-violet-600" />
          <span className="text-sm font-semibold">MCP Connections & Validation</span>
          <Badge variant="purple">v1: registry + health checks</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => testAll.mutate(undefined, {
              onSuccess: (data) =>
                toast({
                  title: "Connection test finished",
                  description: `${data.connected_count} connected, ${data.error_count} failed`,
                }),
            })}
            disabled={!projectId || testAll.isPending}
          >
            {testAll.isPending ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <ShieldCheck className="mr-1 h-3 w-3" />}
            Test All Connections
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowAdd((v) => !v)}>
            <Plus className="mr-1 h-3 w-3" /> Add MCP Connection
          </Button>
        </div>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Register the external systems (APIs, databases, events, applications) your tests will need.
        In this version connections are validated with a real MCP handshake; the Browser MCP is the
        one agents actively use during exploration.
      </p>

      {showAdd && (
        <div className="mb-3 grid grid-cols-1 gap-2 rounded-md border border-border bg-card p-3 md:grid-cols-3">
          <input
            className={inputClass}
            placeholder="Connection name *"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <select
            className={inputClass}
            value={form.connection_type}
            onChange={(e) => setForm({ ...form, connection_type: e.target.value })}
          >
            {Object.entries(TYPE_LABEL).filter(([k]) => k !== "browser").map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <select
            className={inputClass}
            value={form.transport}
            onChange={(e) => setForm({ ...form, transport: e.target.value })}
          >
            <option value="stdio">stdio (npx/uvx launcher)</option>
            <option value="http">http (remote server)</option>
          </select>
          <input
            className={inputClass}
            placeholder="Target label (e.g. Order API SIT)"
            value={form.target}
            onChange={(e) => setForm({ ...form, target: e.target.value })}
          />
          {form.transport === "stdio" ? (
            <>
              <select
                className={inputClass}
                value={form.command}
                onChange={(e) => setForm({ ...form, command: e.target.value })}
              >
                <option value="npx">npx</option>
                <option value="uvx">uvx</option>
                <option value="node">node</option>
                <option value="python">python</option>
              </select>
              <input
                className={inputClass}
                placeholder="Args (e.g. -y @modelcontextprotocol/server-postgres)"
                value={form.argsText}
                onChange={(e) => setForm({ ...form, argsText: e.target.value })}
              />
            </>
          ) : (
            <input
              className={cn(inputClass, "md:col-span-2")}
              placeholder="https://mcp.example.com/mcp"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
            />
          )}
          <textarea
            className={cn(inputClass, "md:col-span-2")}
            rows={2}
            placeholder={"Credentials / env vars (one per line, KEY=value) — stored encrypted"}
            value={form.envText}
            onChange={(e) => setForm({ ...form, envText: e.target.value })}
          />
          <div className="flex items-center gap-2">
            <select
              className={inputClass}
              value={form.access_mode}
              onChange={(e) => setForm({ ...form, access_mode: e.target.value })}
            >
              <option value="read_only">Read-only</option>
              <option value="read_write">Read/Write</option>
            </select>
            <Button size="sm" onClick={handleAdd} disabled={createConnection.isPending || !form.name.trim()}>
              {createConnection.isPending ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
              Save
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-md border border-border bg-card">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-border text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Connection</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Target</th>
              <th className="px-3 py-2 font-medium">Access</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Available To</th>
              <th className="px-3 py-2 font-medium">Tools</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                </td>
              </tr>
            )}
            {!isLoading && connections.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-center text-muted-foreground">
                  No MCP connections yet.
                </td>
              </tr>
            )}
            {connections.map((connection) => (
              <tr key={connection.id} className="border-b border-border/60 last:border-0">
                <td className="px-3 py-2 font-medium">
                  {connection.name}
                  {connection.is_builtin && <Badge variant="purple" className="ml-2">built-in</Badge>}
                </td>
                <td className="px-3 py-2">{TYPE_LABEL[connection.connection_type] ?? connection.connection_type}</td>
                <td className="max-w-[180px] truncate px-3 py-2 text-muted-foreground">
                  {connection.target ?? connection.url ?? connection.command ?? "—"}
                </td>
                <td className="px-3 py-2">
                  {connection.access_mode === "read_write" ? "Read/Write" : "Read-only"}
                </td>
                <td className="px-3 py-2">
                  <Badge variant={statusVariant(connection.status)}>{statusLabel(connection.status)}</Badge>
                </td>
                <td className="px-3 py-2">
                  <span className="flex gap-1">
                    {AGENT_CHIPS.map((chip) => {
                      const enabled = (connection.available_to ?? []).includes(chip.key);
                      return (
                        <span
                          key={chip.key}
                          title={chip.key}
                          className={cn(
                            "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold",
                            enabled ? "bg-violet-100 text-violet-700" : "bg-muted text-muted-foreground/50",
                          )}
                        >
                          {chip.label}
                        </span>
                      );
                    })}
                  </span>
                </td>
                <td className="px-3 py-2">{connection.tool_count ?? "—"}</td>
                <td className="px-3 py-2">
                  <span className="flex items-center justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleTest(connection)}
                      disabled={testingId === connection.id}
                      title="Test connection"
                    >
                      {testingId === connection.id
                        ? <Loader2 className="h-3 w-3 animate-spin" />
                        : <RefreshCw className="h-3 w-3" />}
                    </Button>
                    {!connection.is_builtin && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => deleteConnection.mutate(connection.id)}
                        title="Delete connection"
                      >
                        <Trash2 className="h-3 w-3 text-red-500" />
                      </Button>
                    )}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground">
        {connected}/{connections.length || 0} connected · P = Planner, G = Generator, E = Execution, H = Healer
      </div>
    </div>
  );
}
