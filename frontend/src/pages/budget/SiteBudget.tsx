import { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save, MapPin } from "lucide-react";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  SiteSummary,
  SiteBudgetGrid,
  SiteBudgetSavePayload,
  BudgetVersion,
} from "@/types/api";

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
}

const STATES_ORDER = ["ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];

function groupByState(sites: SiteSummary[]): Map<string, SiteSummary[]> {
  const groups = new Map<string, SiteSummary[]>();
  for (const st of STATES_ORDER) {
    const matching = sites.filter((s) => s.state === st);
    if (matching.length > 0) groups.set(st, matching);
  }
  const noState = sites.filter(
    (s) => !s.state || !STATES_ORDER.includes(s.state)
  );
  if (noState.length > 0) groups.set("Other", noState);
  return groups;
}

export default function SiteBudget() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const queryClient = useQueryClient();
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [localGrid, setLocalGrid] = useState<
    Record<string, Record<string, string>>
  >({});

  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", {
        params: { fy_year: fyYear },
      });
      return res.data;
    },
  });

  const { data: sites, isLoading: sitesLoading } = useQuery<SiteSummary[]>({
    queryKey: ["site-budgets", activeVersionId],
    queryFn: async () => {
      const res = await api.get(
        `/api/v1/budgets/${activeVersionId}/sites`
      );
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  const {
    data: siteGrid,
    isLoading: gridLoading,
  } = useQuery<SiteBudgetGrid>({
    queryKey: ["site-budget-grid", activeVersionId, selectedSiteId],
    queryFn: async () => {
      const res = await api.get(
        `/api/v1/budgets/${activeVersionId}/sites/${selectedSiteId}`
      );
      return res.data;
    },
    enabled: !!activeVersionId && !!selectedSiteId,
  });

  useEffect(() => {
    if (!siteGrid) return;
    const vals: Record<string, Record<string, string>> = {};
    for (const line of siteGrid.lines) {
      const monthVals: Record<string, string> = {};
      for (const p of siteGrid.periods) {
        monthVals[p] = line.values[p] != null ? String(line.values[p]) : "";
      }
      vals[line.line_item] = monthVals;
    }
    setLocalGrid(vals);
  }, [siteGrid]);

  const saveMutation = useMutation({
    mutationFn: async (payload: SiteBudgetSavePayload) => {
      const res = await api.put(
        `/api/v1/budgets/${activeVersionId}/sites/${selectedSiteId}`,
        payload
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["site-budgets", activeVersionId],
      });
      queryClient.invalidateQueries({
        queryKey: ["site-budget-grid", activeVersionId, selectedSiteId],
      });
      queryClient.invalidateQueries({
        queryKey: ["budget-output"],
      });
    },
  });

  const handleSave = useCallback(() => {
    const lines = Object.entries(localGrid).map(([lineItem, monthVals]) => ({
      line_item: lineItem,
      values: Object.fromEntries(
        Object.entries(monthVals)
          .map(([k, v]) => [k, parseFloat(v)])
          .filter(([, v]) => !isNaN(v as number))
      ) as Record<string, number>,
    }));
    saveMutation.mutate({ lines });
  }, [localGrid, saveMutation]);

  const updateCell = useCallback(
    (lineItem: string, period: string, value: string) => {
      setLocalGrid((prev) => ({
        ...prev,
        [lineItem]: { ...(prev[lineItem] ?? {}), [period]: value },
      }));
    },
    []
  );

  const activeVersion = versions?.find((v) => v.id === activeVersionId);
  const stateGroups = sites ? groupByState(sites) : new Map<string, SiteSummary[]>();

  const siteTotalRevenue = (site: SiteSummary): number =>
    Object.values(site.monthly_totals).reduce((a, b) => a + b, 0);

  // Compute summary row: total across all sites per period
  const summaryByPeriod: Record<string, number> = {};
  if (sites && siteGrid) {
    for (const site of sites) {
      for (const [period, amount] of Object.entries(site.monthly_totals)) {
        summaryByPeriod[period] = (summaryByPeriod[period] ?? 0) + amount;
      }
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Site Budgets</h1>
        <p className="text-muted-foreground">
          FY{fyYear}
          {activeVersion && <> &middot; {activeVersion.name}</>}
          {" "}&middot; Enter budgets per site, rolled up to entity totals
        </p>
      </div>

      {!activeVersionId && (
        <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
          Select a budget version on the Assumptions page first.
        </div>
      )}

      {activeVersionId && (
        <div className="flex gap-6">
          {/* Left panel — site list grouped by state */}
          <div className="w-72 shrink-0 space-y-1 max-h-[calc(100vh-200px)] overflow-y-auto">
            {sitesLoading && (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            )}

            {[...stateGroups.entries()].map(([state, stateSites]) => (
              <div key={state} className="mb-3">
                <div className="mb-1 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                  {state}
                </div>
                {stateSites.map((site) => {
                  const totalRev = siteTotalRevenue(site);
                  return (
                    <button
                      key={site.location_id}
                      onClick={() => setSelectedSiteId(site.location_id)}
                      className={`w-full text-left rounded-md px-3 py-2 text-sm transition-colors ${
                        site.location_id === selectedSiteId
                          ? "bg-primary text-primary-foreground"
                          : "text-foreground hover:bg-accent/50"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1.5 truncate">
                          <MapPin className="h-3 w-3 shrink-0 opacity-60" />
                          {site.name}
                        </span>
                        {totalRev > 0 && (
                          <span
                            className={`text-xs tabular-nums ml-2 ${
                              site.location_id === selectedSiteId
                                ? "text-primary-foreground/70"
                                : "text-muted-foreground"
                            }`}
                          >
                            {fmtAUD(totalRev)}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            ))}

            {sites && sites.length === 0 && (
              <div className="rounded-lg border bg-card p-4 text-center text-sm text-muted-foreground">
                No sites found. Run the seed_locations script.
              </div>
            )}
          </div>

          {/* Right panel — 12-month budget grid */}
          <div className="flex-1 min-w-0">
            {!selectedSiteId && (
              <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
                Select a site from the list to enter budget amounts.
              </div>
            )}

            {selectedSiteId && gridLoading && (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            )}

            {selectedSiteId && siteGrid && (
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">
                      {siteGrid.location_name}
                    </CardTitle>
                    <Button
                      size="sm"
                      onClick={handleSave}
                      disabled={saveMutation.isPending}
                    >
                      {saveMutation.isPending ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Save className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      Save
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/50">
                          <th className="px-3 py-2 text-left font-medium sticky left-0 bg-muted/50 z-10 min-w-[160px]">
                            Line Item
                          </th>
                          {siteGrid.periods.map((p) => (
                            <th
                              key={p}
                              className="px-2 py-2 text-center font-medium whitespace-nowrap min-w-[90px]"
                            >
                              {p}
                            </th>
                          ))}
                          <th className="px-3 py-2 text-right font-medium min-w-[100px]">
                            Total
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {siteGrid.lines.map((line) => {
                          const isRevenue = line.line_item
                            .toLowerCase()
                            .includes("revenue");
                          const lineTotal = siteGrid.periods.reduce(
                            (sum, p) => {
                              const v = parseFloat(
                                localGrid[line.line_item]?.[p] ?? "0"
                              );
                              return sum + (isNaN(v) ? 0 : v);
                            },
                            0
                          );

                          return (
                            <tr
                              key={line.line_item}
                              className="border-b last:border-0"
                            >
                              <td
                                className={`px-3 py-1.5 sticky left-0 bg-background z-10 whitespace-nowrap font-medium ${
                                  isRevenue
                                    ? "text-foreground"
                                    : "text-muted-foreground"
                                }`}
                              >
                                {line.line_item}
                              </td>
                              {siteGrid.periods.map((p) => (
                                <td key={p} className="px-1 py-1">
                                  <input
                                    type="text"
                                    inputMode="decimal"
                                    className="w-full rounded border border-input bg-transparent px-2 py-1 text-center text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
                                    value={
                                      localGrid[line.line_item]?.[p] ?? ""
                                    }
                                    onChange={(e) =>
                                      updateCell(
                                        line.line_item,
                                        p,
                                        e.target.value
                                      )
                                    }
                                  />
                                </td>
                              ))}
                              <td className="px-3 py-1.5 text-right tabular-nums font-medium">
                                {fmtAUD(lineTotal)}
                              </td>
                            </tr>
                          );
                        })}

                        {/* Net margin row */}
                        {siteGrid.periods.length > 0 && (
                          <tr className="border-t-2 bg-muted/30">
                            <td className="px-3 py-2 sticky left-0 bg-muted/30 z-10 font-semibold">
                              Net Site Margin
                            </td>
                            {siteGrid.periods.map((p) => {
                              let net = 0;
                              for (const line of siteGrid.lines) {
                                const v = parseFloat(
                                  localGrid[line.line_item]?.[p] ?? "0"
                                );
                                if (isNaN(v)) continue;
                                const isRev = line.line_item
                                  .toLowerCase()
                                  .includes("revenue");
                                net += isRev ? v : -v;
                              }
                              return (
                                <td
                                  key={p}
                                  className={`px-2 py-2 text-center tabular-nums font-semibold ${
                                    net < 0 ? "text-red-600" : ""
                                  }`}
                                >
                                  {fmtAUD(net)}
                                </td>
                              );
                            })}
                            <td className="px-3 py-2 text-right tabular-nums font-semibold">
                              {fmtAUD(
                                siteGrid.periods.reduce((sum, p) => {
                                  let net = 0;
                                  for (const line of siteGrid.lines) {
                                    const v = parseFloat(
                                      localGrid[line.line_item]?.[p] ?? "0"
                                    );
                                    if (isNaN(v)) continue;
                                    const isRev = line.line_item
                                      .toLowerCase()
                                      .includes("revenue");
                                    net += isRev ? v : -v;
                                  }
                                  return sum + net;
                                }, 0)
                              )}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* All-sites summary */}
                  {Object.keys(summaryByPeriod).length > 0 && (
                    <div className="mt-6">
                      <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                        All Sites — Total Revenue
                      </h3>
                      <div className="overflow-x-auto rounded-lg border">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b bg-muted/50">
                              <th className="px-3 py-2 text-left font-medium sticky left-0 bg-muted/50 z-10 min-w-[160px]">
                                Metric
                              </th>
                              {siteGrid.periods.map((p) => (
                                <th
                                  key={p}
                                  className="px-2 py-2 text-center font-medium whitespace-nowrap min-w-[90px]"
                                >
                                  {p}
                                </th>
                              ))}
                              <th className="px-3 py-2 text-right font-medium min-w-[100px]">
                                Total
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr className="border-b">
                              <td className="px-3 py-1.5 sticky left-0 bg-background z-10 font-medium">
                                Total Budget Revenue
                              </td>
                              {siteGrid.periods.map((p) => (
                                <td
                                  key={p}
                                  className="px-2 py-1.5 text-center tabular-nums"
                                >
                                  {fmtAUD(summaryByPeriod[p] ?? 0)}
                                </td>
                              ))}
                              <td className="px-3 py-1.5 text-right tabular-nums font-medium">
                                {fmtAUD(
                                  Object.values(summaryByPeriod).reduce(
                                    (a, b) => a + b,
                                    0
                                  )
                                )}
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
