import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Loader2, AlertCircle, CheckCircle2, Clock } from "lucide-react";
import api from "@/utils/api";
import { usePeriodStore } from "@/stores/period";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import type { SyncRunRead, EntityRead } from "@/types/api";

function statusBadge(status: string | null) {
  const base =
    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium";
  switch (status) {
    case "success":
      return { cls: `${base} bg-emerald-100 text-emerald-800`, icon: CheckCircle2 };
    case "failed":
      return { cls: `${base} bg-red-100 text-red-800`, icon: AlertCircle };
    case "partial":
      return { cls: `${base} bg-amber-100 text-amber-800`, icon: AlertCircle };
    case "running":
      return { cls: `${base} bg-blue-100 text-blue-800`, icon: Loader2 };
    default:
      return { cls: `${base} bg-gray-100 text-gray-800`, icon: Clock };
  }
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-AU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const hrs = Math.floor(diff / 3_600_000);
  if (hrs < 1) return "< 1 hr ago";
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

interface EntitySyncRow {
  entity: EntityRead;
  lastRun: SyncRunRead | null;
}

export default function SyncRuns() {
  const { fyYear, fyMonth } = usePeriodStore();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());

  const entities = useQuery<EntityRead[]>({
    queryKey: ["entities"],
    queryFn: async () => (await api.get("/api/v1/entities")).data,
  });

  const syncRuns = useQuery<SyncRunRead[]>({
    queryKey: ["sync-runs"],
    queryFn: async () => (await api.get("/api/v1/sync/runs")).data,
    refetchInterval: 30_000,
  });

  const triggerSync = useMutation({
    mutationFn: async (entity: EntityRead) => {
      const source = entity.source_system ?? "netsuite";
      return api.post(`/api/v1/sync/${source}/${entity.id}`, {
        fy_year: fyYear,
        fy_month: fyMonth,
      });
    },
    onMutate: (entity) => {
      setSyncingIds((prev) => new Set(prev).add(entity.id));
    },
    onSettled: (_data, _err, entity) => {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(entity.id);
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
    },
  });

  // FIX(L8): sort runs by started_at descending so [0] is truly the latest
  const entityRows: EntitySyncRow[] = (entities.data ?? []).map((ent) => {
    const runs = (syncRuns.data ?? [])
      .filter((r) => r.entity_id === ent.id)
      .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
    return { entity: ent, lastRun: runs[0] ?? null };
  });

  const isLoading = entities.isLoading || syncRuns.isLoading;
  const isError = entities.isError || syncRuns.isError;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Sync Status</h1>
          <p className="text-muted-foreground">
            Data synchronisation status for each entity.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
          }}
          disabled={syncRuns.isFetching}
        >
          <RefreshCw
            className={`mr-2 h-3.5 w-3.5 ${syncRuns.isFetching ? "animate-spin" : ""}`}
          />
          Refresh
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Failed to load sync data.</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => {
              entities.refetch();
              syncRuns.refetch();
            }}
          >
            Retry
          </Button>
        </div>
      )}

      {!isLoading && !isError && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">Entity</th>
                <th className="px-4 py-3 text-left font-medium">Source</th>
                <th className="px-4 py-3 text-left font-medium">Last Sync</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Records</th>
                <th className="px-4 py-3 text-left font-medium">Error</th>
                {isAdmin && (
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                )}
              </tr>
            </thead>
            <tbody>
              {entityRows.map(({ entity, lastRun }) => {
                const badge = statusBadge(lastRun?.status ?? null);
                const BadgeIcon = badge.icon;
                const isSyncing = syncingIds.has(entity.id) || lastRun?.status === "running";
                const completedAt = lastRun?.completed_at;
                const isStale =
                  completedAt &&
                  Date.now() - new Date(completedAt).getTime() > 25 * 3_600_000;

                return (
                  <tr key={entity.id} className="border-b last:border-0">
                    <td className="px-4 py-2">
                      <div>
                        <span className="font-medium">{entity.code}</span>
                        {entity.name && (
                          <span className="ml-2 text-muted-foreground text-xs">
                            {entity.name}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2 capitalize text-muted-foreground">
                      {entity.source_system ?? "—"}
                    </td>
                    <td className="px-4 py-2">
                      <div className="text-muted-foreground">
                        {fmtDate(completedAt ?? null)}
                      </div>
                      {completedAt && (
                        <div
                          className={`text-xs ${isStale ? "text-amber-600 font-medium" : "text-muted-foreground"}`}
                        >
                          {timeAgo(completedAt)}
                          {isStale && " — stale"}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {lastRun ? (
                        <span className={badge.cls}>
                          <BadgeIcon
                            className={`h-3 w-3 ${lastRun.status === "running" ? "animate-spin" : ""}`}
                          />
                          {lastRun.status}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          Never synced
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {lastRun?.records_upserted ?? "—"}
                    </td>
                    <td className="px-4 py-2 max-w-[200px]">
                      {lastRun?.error_detail ? (
                        <span
                          className="text-xs text-destructive truncate block"
                          title={lastRun.error_detail}
                        >
                          {lastRun.error_detail}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="px-4 py-2 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={isSyncing}
                          onClick={() => triggerSync.mutate(entity)}
                        >
                          {isSyncing ? (
                            <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                          ) : (
                            <RefreshCw className="mr-1.5 h-3 w-3" />
                          )}
                          Sync Now
                        </Button>
                      </td>
                    )}
                  </tr>
                );
              })}
              {entityRows.length === 0 && (
                <tr>
                  <td
                    colSpan={isAdmin ? 7 : 6}
                    className="px-4 py-8 text-center text-muted-foreground"
                  >
                    No entities configured.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Recent runs detail */}
      {syncRuns.data && syncRuns.data.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Recent Runs</h2>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium">Entity</th>
                  <th className="px-4 py-3 text-left font-medium">Source</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Records</th>
                  <th className="px-4 py-3 text-left font-medium">Started</th>
                  <th className="px-4 py-3 text-left font-medium">Completed</th>
                  <th className="px-4 py-3 text-left font-medium">Triggered</th>
                </tr>
              </thead>
              <tbody>
                {syncRuns.data.map((run) => {
                  const badge = statusBadge(run.status);
                  const BadgeIcon = badge.icon;
                  return (
                    <tr key={run.id} className="border-b last:border-0">
                      <td className="px-4 py-2 font-medium">
                        {run.entity_code ?? "—"}
                      </td>
                      <td className="px-4 py-2 capitalize text-muted-foreground">
                        {run.source_system ?? "—"}
                      </td>
                      <td className="px-4 py-2">
                        <span className={badge.cls}>
                          <BadgeIcon
                            className={`h-3 w-3 ${run.status === "running" ? "animate-spin" : ""}`}
                          />
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
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
