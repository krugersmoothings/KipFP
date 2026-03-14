import { useQuery } from "@tanstack/react-query";
import api from "@/utils/api";
import type { SyncRunRead } from "@/types/api";

function statusBadge(status: string | null) {
  const base = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium";
  switch (status) {
    case "success":
      return `${base} bg-emerald-100 text-emerald-800`;
    case "failed":
      return `${base} bg-red-100 text-red-800`;
    case "running":
      return `${base} bg-blue-100 text-blue-800`;
    default:
      return `${base} bg-gray-100 text-gray-800`;
  }
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function SyncRuns() {
  const { data, isLoading, error } = useQuery<SyncRunRead[]>({
    queryKey: ["sync-runs"],
    queryFn: async () => {
      const res = await api.get("/api/v1/sync/runs");
      return res.data;
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Sync Runs</h1>
        <p className="text-muted-foreground">
          Recent data synchronisation activity from connected sources.
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          Loading...
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load sync runs.
        </div>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">Source</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Records</th>
                <th className="px-4 py-3 text-left font-medium">Started</th>
                <th className="px-4 py-3 text-left font-medium">Completed</th>
                <th className="px-4 py-3 text-left font-medium">Triggered By</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id} className="border-b last:border-0">
                  <td className="px-4 py-2 capitalize">
                    {run.source_system ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <span className={statusBadge(run.status)}>
                      {run.status ?? "unknown"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {run.records_upserted}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {fmtDate(run.started_at)}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {fmtDate(run.completed_at)}
                  </td>
                  <td className="px-4 py-2 capitalize text-muted-foreground">
                    {run.triggered_by}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No sync runs recorded yet.
        </div>
      )}
    </div>
  );
}
