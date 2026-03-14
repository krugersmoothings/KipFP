import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { WcDriverRead, WcDriverUpdate, BudgetVersion } from "@/types/api";

const MONTHS = [
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
];

const DRIVER_LABELS: Record<string, string> = {
  dso: "Debtors DSO",
  dpo: "Creditors DPO",
  dii: "Inventory DII",
  fixed_balance: "Fixed Balance",
  pct_revenue: "% of Revenue",
};

function effectiveDays(baseDays: number, factor: number): number {
  return Math.round(baseDays * factor * 10) / 10;
}

export default function WorkingCapital() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const queryClient = useQueryClient();
  const [editMode, setEditMode] = useState<"base" | "monthly">("base");
  const [localDrivers, setLocalDrivers] = useState<
    Record<string, { baseDays: string; factors: string[] }>
  >({});

  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const { data: drivers, isLoading } = useQuery<WcDriverRead[]>({
    queryKey: ["wc-drivers", activeVersionId],
    queryFn: async () => {
      const res = await api.get(`/api/v1/budgets/${activeVersionId}/wc-drivers`);
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  const initLocal = useCallback(
    (drvs: WcDriverRead[]) => {
      const result: Record<string, { baseDays: string; factors: string[] }> = {};
      for (const d of drvs) {
        const factors = Array.from({ length: 12 }, (_, i) => {
          if (Array.isArray(d.seasonal_factors) && d.seasonal_factors[i] != null) {
            return String(d.seasonal_factors[i]);
          }
          if (
            d.seasonal_factors &&
            !Array.isArray(d.seasonal_factors)
          ) {
            const val =
              (d.seasonal_factors as Record<string, number>)[String(i + 1)] ??
              (d.seasonal_factors as Record<string, number>)[String(i)];
            if (val != null) return String(val);
          }
          return "1";
        });
        result[d.id] = {
          baseDays: String(d.base_days ?? ""),
          factors,
        };
      }
      setLocalDrivers(result);
    },
    []
  );

  const prevDriversRef = useState<string>("");
  if (drivers && JSON.stringify(drivers) !== prevDriversRef[0]) {
    prevDriversRef[1](JSON.stringify(drivers));
    initLocal(drivers);
  }

  const saveMutation = useMutation({
    mutationFn: async (updates: WcDriverUpdate[]) => {
      await api.put(`/api/v1/budgets/${activeVersionId}/wc-drivers`, updates);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wc-drivers", activeVersionId] });
    },
  });

  const handleSave = useCallback(() => {
    if (!drivers) return;
    const updates: WcDriverUpdate[] = drivers.map((d) => {
      const local = localDrivers[d.id];
      return {
        id: d.id,
        base_days: local ? parseFloat(local.baseDays) || null : d.base_days,
        seasonal_factors: local
          ? Object.fromEntries(
              local.factors.map((f, i) => [String(i + 1), parseFloat(f) || 1])
            )
          : d.seasonal_factors,
      };
    });
    saveMutation.mutate(updates);
  }, [drivers, localDrivers, saveMutation, activeVersionId]);

  const activeVersion = versions?.find((v) => v.id === activeVersionId);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Working Capital Assumptions
          </h1>
          <p className="text-muted-foreground">
            FY{fyYear}
            {activeVersion && <> &middot; {activeVersion.name}</>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border overflow-hidden">
            <button
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                editMode === "base"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
              onClick={() => setEditMode("base")}
            >
              Base Days
            </button>
            <button
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                editMode === "monthly"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
              onClick={() => setEditMode("monthly")}
            >
              Monthly Override
            </button>
          </div>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending || !activeVersionId}
          >
            {saveMutation.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-3.5 w-3.5" />
            )}
            Save
          </Button>
        </div>
      </div>

      {!activeVersionId && (
        <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
          Select a budget version on the Assumptions page first.
        </div>
      )}

      {activeVersionId && isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {activeVersionId && drivers && drivers.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No working capital drivers configured for this version.
        </div>
      )}

      {activeVersionId && drivers && drivers.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">WC Drivers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium sticky left-0 bg-muted/50 z-10 min-w-[200px]">
                      Driver
                    </th>
                    <th className="px-3 py-2 text-left font-medium min-w-[80px]">
                      Type
                    </th>
                    {editMode === "base" && (
                      <th className="px-3 py-2 text-center font-medium min-w-[90px]">
                        Base Days
                      </th>
                    )}
                    {MONTHS.map((m) => (
                      <th
                        key={m}
                        className="px-2 py-2 text-center font-medium whitespace-nowrap min-w-[80px]"
                      >
                        {m}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {drivers.map((d) => {
                    const local = localDrivers[d.id];
                    const baseDays = parseFloat(local?.baseDays ?? "0") || 0;

                    return (
                      <tr key={d.id} className="border-b last:border-0">
                        <td className="px-3 py-1.5 sticky left-0 bg-background z-10 font-medium whitespace-nowrap">
                          {d.account_label || d.account_id}
                        </td>
                        <td className="px-3 py-1.5 text-muted-foreground text-xs">
                          {DRIVER_LABELS[d.driver_type] ?? d.driver_type}
                        </td>
                        {editMode === "base" && (
                          <td className="px-1 py-1">
                            <input
                              type="text"
                              inputMode="decimal"
                              className="w-full rounded border border-input bg-transparent px-2 py-1 text-center text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
                              value={local?.baseDays ?? ""}
                              onChange={(e) =>
                                setLocalDrivers((prev) => ({
                                  ...prev,
                                  [d.id]: {
                                    ...prev[d.id],
                                    baseDays: e.target.value,
                                  },
                                }))
                              }
                            />
                          </td>
                        )}
                        {MONTHS.map((_, mi) => {
                          const factor = parseFloat(local?.factors[mi] ?? "1") || 1;
                          const eff = effectiveDays(baseDays, factor);

                          if (editMode === "monthly") {
                            return (
                              <td key={mi} className="px-1 py-1">
                                <input
                                  type="text"
                                  inputMode="decimal"
                                  className="w-full rounded border border-input bg-transparent px-2 py-1 text-center text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
                                  value={local?.factors[mi] ?? "1"}
                                  onChange={(e) =>
                                    setLocalDrivers((prev) => {
                                      const f = [...(prev[d.id]?.factors ?? [])];
                                      f[mi] = e.target.value;
                                      return {
                                        ...prev,
                                        [d.id]: { ...prev[d.id], factors: f },
                                      };
                                    })
                                  }
                                />
                              </td>
                            );
                          }

                          return (
                            <td
                              key={mi}
                              className="px-2 py-1.5 text-center tabular-nums text-muted-foreground"
                            >
                              {eff}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
