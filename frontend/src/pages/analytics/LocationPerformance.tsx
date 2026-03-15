import React, { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import { Download, Loader2, AlertTriangle, Building2, DollarSign, TrendingUp, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePeriodStore } from "@/stores/period";
import { useAppStore } from "@/stores/app";
import api from "@/utils/api";
import type { LocationPerformanceRow, LocationTimeSeriesPoint, BudgetVersion } from "@/types/api";

type SortBy = "revenue" | "site_pl" | "variance_pct" | "alphabetical";
type ViewMode = "chart" | "table" | "both";

// FIX(L15): include all Australian states/territories
const STATES = ["ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];

const fmtCurrency = (v: number) =>
  new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", maximumFractionDigits: 0 }).format(v);

const fmtPct = (v: number | null) =>
  v != null ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : "—";

function SparkLine({ data }: { data: LocationTimeSeriesPoint[] }) {
  // FIX(M37): handle single data point (avoids 0/0 = NaN)
  if (!data || data.length === 0) return <span className="text-muted-foreground">—</span>;
  const values = data.map((d) => d.site_pl);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const width = 80;
  const height = 24;
  const denominator = values.length > 1 ? values.length - 1 : 1;
  const points = values
    .map((v, i) => {
      const x = (i / denominator) * width;
      const y = height - ((v - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  const lastVal = values[values.length - 1];
  const color = lastVal >= 0 ? "#16a34a" : "#dc2626";

  return (
    <svg width={width} height={height} className="inline-block">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={points} />
    </svg>
  );
}

export default function LocationPerformance() {
  const navigate = useNavigate();
  const { fyYear, fyMonth } = usePeriodStore();
  const { includeAasb16 } = useAppStore();

  const [useFullYear, setUseFullYear] = useState(false);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [stateFilter, setStateFilter] = useState<Set<string>>(new Set());
  const [sortBy, setSortBy] = useState<SortBy>("site_pl");
  const [viewMode, setViewMode] = useState<ViewMode>("both");
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [filterAdverse, setFilterAdverse] = useState(false);
  const [exporting, setExporting] = useState(false);

  const toggleState = (s: string) => {
    setStateFilter((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  // Load budget versions for comparison selector
  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", {
        params: { fy_year: fyYear },
      });
      return res.data;
    },
  });

  // Load location data
  const { data: locations, isLoading } = useQuery<LocationPerformanceRow[]>({
    queryKey: ["analytics-locations", fyYear, useFullYear ? null : fyMonth, versionId, includeAasb16],
    queryFn: async () => {
      const params: Record<string, string | number | boolean> = { fy_year: fyYear, include_aasb16: includeAasb16 };
      if (!useFullYear) params.fy_month = fyMonth;
      if (versionId) params.version_id = versionId;
      const res = await api.get("/api/v1/analytics/locations", { params });
      return res.data;
    },
  });

  // Load sparkline data for expanded row
  const { data: expandedTimeseries } = useQuery<LocationTimeSeriesPoint[]>({
    queryKey: ["analytics-location-ts", expandedRow, fyYear],
    queryFn: async () => {
      const fromFy = fyYear - 1;
      const res = await api.get(`/api/v1/analytics/locations/${expandedRow}/timeseries`, {
        params: { from_fy_year: fromFy, from_fy_month: 1, to_fy_year: fyYear, to_fy_month: 12 },
      });
      return res.data;
    },
    enabled: !!expandedRow,
  });

  // Filter and sort
  const filteredLocations = useMemo(() => {
    if (!locations) return [];
    let filtered = [...locations];
    if (stateFilter.size > 0) {
      filtered = filtered.filter((l) => l.state && stateFilter.has(l.state));
    }
    if (filterAdverse) {
      filtered = filtered.filter(
        (l) => l.variance_pct != null && l.variance_pct < -10
      );
    }
    switch (sortBy) {
      case "revenue":
        filtered.sort((a, b) => b.revenue - a.revenue);
        break;
      case "site_pl":
        filtered.sort((a, b) => b.site_pl - a.site_pl);
        break;
      case "variance_pct":
        filtered.sort(
          (a, b) => (b.variance_pct ?? -Infinity) - (a.variance_pct ?? -Infinity)
        );
        break;
      case "alphabetical":
        filtered.sort((a, b) =>
          (a.location_name ?? "").localeCompare(b.location_name ?? "")
        );
        break;
    }
    return filtered;
  }, [locations, stateFilter, sortBy, filterAdverse]);

  // Summary cards
  const summary = useMemo(() => {
    if (!locations) return { totalSites: 0, groupRevenue: 0, groupSitePL: 0, adverseCount: 0 };
    const adverseCount = locations.filter(
      (l) => l.variance_pct != null && l.variance_pct < -10
    ).length;
    return {
      totalSites: locations.length,
      groupRevenue: locations.reduce((sum, l) => sum + l.revenue, 0),
      groupSitePL: locations.reduce((sum, l) => sum + l.site_pl, 0),
      adverseCount,
    };
  }, [locations]);

  // Chart data (horizontal bar)
  const chartData = useMemo(() => {
    return filteredLocations.map((l) => ({
      name: l.location_code || l.location_name || "Unknown",
      site_pl: l.site_pl,
      budget_pl: l.budget_site_pl,
      location_id: l.location_id,
      state: l.state,
    }));
  }, [filteredLocations]);

  const handleBarClick = (_data: unknown, index: number) => {
    const loc = chartData[index];
    if (loc?.location_id) {
      navigate(`/analytics/timeseries?location=${loc.location_id}`);
    }
  };

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const res = await api.post(
        "/api/v1/analytics/export",
        {
          report_type: "locations",
          params: { fy_year: fyYear, fy_month: useFullYear ? undefined : fyMonth },
          format: "xlsx",
        },
        { responseType: "blob" }
      );
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "kip_analytics_locations.xlsx");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [fyYear, fyMonth, useFullYear]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Location Performance</h1>
          <p className="text-muted-foreground">
            Site-level P&L analysis &middot; FY{fyYear}
            {!useFullYear && ` M${String(fyMonth).padStart(2, "0")}`}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
          {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
          Export Excel
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Building2 className="h-4 w-4" />
            Total Sites
          </div>
          <p className="mt-1 text-2xl font-bold">{summary.totalSites}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <DollarSign className="h-4 w-4" />
            Group Revenue
          </div>
          <p className="mt-1 text-2xl font-bold">{fmtCurrency(summary.groupRevenue)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <TrendingUp className="h-4 w-4" />
            Group Site P&L
          </div>
          <p className={`mt-1 text-2xl font-bold ${summary.groupSitePL >= 0 ? "text-emerald-600" : "text-red-600"}`}>
            {fmtCurrency(summary.groupSitePL)}
          </p>
        </div>
        <button
          onClick={() => setFilterAdverse(!filterAdverse)}
          className="rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent"
        >
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <AlertTriangle className="h-4 w-4" />
            Adverse Variance {">"} 10%
          </div>
          <p className={`mt-1 text-2xl font-bold ${summary.adverseCount > 0 ? "text-red-600" : ""}`}>
            {summary.adverseCount}
          </p>
          {filterAdverse && <p className="mt-1 text-xs text-primary">Filtering active</p>}
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border bg-card p-4">
        {/* Period selector */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Period</label>
          <div className="flex gap-1">
            <button
              onClick={() => setUseFullYear(false)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                !useFullYear ? "bg-primary text-primary-foreground" : "border bg-background text-muted-foreground hover:bg-accent"
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setUseFullYear(true)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                useFullYear ? "bg-primary text-primary-foreground" : "border bg-background text-muted-foreground hover:bg-accent"
              }`}
            >
              Full Year
            </button>
          </div>
        </div>

        {/* Budget version */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Budget Version</label>
          <select
            value={versionId ?? ""}
            onChange={(e) => setVersionId(e.target.value || null)}
            className="rounded-md border bg-background px-2 py-1.5 text-xs"
          >
            <option value="">No comparison</option>
            {versions?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} (FY{v.fy_year})
              </option>
            ))}
          </select>
        </div>

        {/* State filter */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">State</label>
          <div className="flex gap-1">
            <button
              onClick={() => setStateFilter(new Set())}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                stateFilter.size === 0 ? "bg-primary text-primary-foreground" : "border bg-background text-muted-foreground hover:bg-accent"
              }`}
            >
              All
            </button>
            {STATES.map((s) => (
              <button
                key={s}
                onClick={() => toggleState(s)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  stateFilter.has(s) ? "bg-primary text-primary-foreground" : "border bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Sort by */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Sort By</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortBy)}
            className="rounded-md border bg-background px-2 py-1.5 text-xs"
          >
            <option value="site_pl">Site P&L</option>
            <option value="revenue">Revenue</option>
            <option value="variance_pct">Variance %</option>
            <option value="alphabetical">Alphabetical</option>
          </select>
        </div>

        {/* View toggle */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">View</label>
          <div className="flex gap-1">
            {(["chart", "table", "both"] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                  viewMode === mode ? "bg-primary text-primary-foreground" : "border bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Horizontal bar chart */}
      {!isLoading && (viewMode === "chart" || viewMode === "both") && chartData.length > 0 && (
        <div className="rounded-lg border bg-card p-4">
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 32 + 40)}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" horizontal={false} />
              <XAxis
                type="number"
                tickFormatter={(v: number) => fmtCurrency(v)}
                tick={{ fontSize: 11 }}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 11 }}
                width={90}
              />
              <Tooltip
                formatter={(value) => fmtCurrency(Number(value))}
                labelStyle={{ fontWeight: 600 }}
              />
              <ReferenceLine x={0} stroke="#888" />
              <Bar
                dataKey="site_pl"
                name="Site P&L"
                onClick={handleBarClick}
                cursor="pointer"
                radius={[0, 4, 4, 0]}
              >
                {chartData.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={entry.site_pl >= 0 ? "#16a34a" : "#dc2626"}
                    fillOpacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      {!isLoading && (viewMode === "table" || viewMode === "both") && filteredLocations.length > 0 && (
        <div className="rounded-lg border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium">Site</th>
                  <th className="px-4 py-3 text-left font-medium">State</th>
                  <th className="px-4 py-3 text-left font-medium">Entity</th>
                  <th className="px-4 py-3 text-right font-medium">Revenue</th>
                  <th className="px-4 py-3 text-right font-medium">Direct Costs</th>
                  <th className="px-4 py-3 text-right font-medium">Site P&L</th>
                  {versionId && (
                    <>
                      <th className="px-4 py-3 text-right font-medium">Budget P&L</th>
                      <th className="px-4 py-3 text-right font-medium">Var $</th>
                      <th className="px-4 py-3 text-right font-medium">Var %</th>
                    </>
                  )}
                  <th className="px-4 py-3 text-center font-medium">Trend</th>
                </tr>
              </thead>
              <tbody>
                {filteredLocations.map((loc) => {
                  const isExpanded = expandedRow === loc.location_id;
                  return (
                    <React.Fragment key={loc.location_id}>
                      <tr
                        onClick={() => setExpandedRow(isExpanded ? null : loc.location_id)}
                        className="cursor-pointer border-b transition-colors hover:bg-muted/30"
                      >
                        <td className="px-4 py-2.5 font-medium">
                          <div className="flex items-center gap-2">
                            <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
                            {loc.location_name || loc.location_code}
                          </div>
                        </td>
                        <td className="px-4 py-2.5">{loc.state ?? "—"}</td>
                        <td className="px-4 py-2.5">{loc.entity_code ?? "—"}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{fmtCurrency(loc.revenue)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{fmtCurrency(loc.direct_costs)}</td>
                        <td
                          className={`px-4 py-2.5 text-right tabular-nums font-medium ${
                            loc.site_pl >= 0 ? "text-emerald-600" : "text-red-600"
                          }`}
                        >
                          {fmtCurrency(loc.site_pl)}
                        </td>
                        {versionId && (
                          <>
                            <td className="px-4 py-2.5 text-right tabular-nums">
                              {loc.budget_site_pl != null ? fmtCurrency(loc.budget_site_pl) : "—"}
                            </td>
                            <td
                              className={`px-4 py-2.5 text-right tabular-nums ${
                                loc.is_favourable === true
                                  ? "text-emerald-600"
                                  : loc.is_favourable === false
                                  ? "text-red-600"
                                  : ""
                              }`}
                            >
                              {loc.variance_abs != null ? fmtCurrency(loc.variance_abs) : "—"}
                            </td>
                            <td
                              className={`px-4 py-2.5 text-right tabular-nums ${
                                loc.is_favourable === true
                                  ? "text-emerald-600"
                                  : loc.is_favourable === false
                                  ? "text-red-600"
                                  : ""
                              }`}
                            >
                              {fmtPct(loc.variance_pct)}
                            </td>
                          </>
                        )}
                        <td className="px-4 py-2.5 text-center">
                          {isExpanded && expandedTimeseries ? (
                            <SparkLine data={expandedTimeseries.slice(-6)} />
                          ) : (
                            <span className="text-xs text-muted-foreground">click to expand</span>
                          )}
                        </td>
                      </tr>
                      {isExpanded && expandedTimeseries && (
                        <tr key={`${loc.location_id}-detail`} className="border-b bg-muted/20">
                          <td colSpan={versionId ? 10 : 7} className="px-4 py-3">
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="border-b">
                                    <th className="px-3 py-2 text-left font-medium">Period</th>
                                    <th className="px-3 py-2 text-right font-medium">Revenue</th>
                                    <th className="px-3 py-2 text-right font-medium">Direct Costs</th>
                                    <th className="px-3 py-2 text-right font-medium">Site P&L</th>
                                    <th className="px-3 py-2 text-right font-medium">MoM %</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {expandedTimeseries.map((pt, idx) => (
                                    <tr key={idx} className="border-b">
                                      <td className="px-3 py-1.5">{pt.period_label}</td>
                                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtCurrency(pt.revenue)}</td>
                                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtCurrency(pt.direct_costs)}</td>
                                      <td
                                        className={`px-3 py-1.5 text-right tabular-nums ${
                                          pt.site_pl >= 0 ? "text-emerald-600" : "text-red-600"
                                        }`}
                                      >
                                        {fmtCurrency(pt.site_pl)}
                                      </td>
                                      <td className="px-3 py-1.5 text-right tabular-nums">
                                        {fmtPct(pt.mom_change_pct)}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            <div className="mt-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  navigate(`/analytics/timeseries?location=${loc.location_id}`);
                                }}
                              >
                                View full time series
                              </Button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!isLoading && filteredLocations.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No locations found for the selected period and filters.
        </div>
      )}
    </div>
  );
}
