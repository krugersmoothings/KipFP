import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePeriodStore } from "@/stores/period";
import { useAppStore } from "@/stores/app";
import api from "@/utils/api";
import type { EntityRead, TimeSeriesPoint, MultiTimeSeriesResponse } from "@/types/api";

type Metric = "revenue" | "gm" | "ebitda" | "npat";
type ViewMode = "chart" | "table" | "both";

const METRIC_CONFIG: Record<Metric, { label: string; color: string; priorColor: string }> = {
  revenue: { label: "Revenue", color: "#2563eb", priorColor: "#93c5fd" },
  gm: { label: "Gross Margin", color: "#16a34a", priorColor: "#86efac" },
  ebitda: { label: "EBITDA", color: "#9333ea", priorColor: "#c4b5fd" },
  npat: { label: "NPAT", color: "#ea580c", priorColor: "#fdba74" },
};


// FIX(L13): compute inside component or use a function to avoid stale module-level value
function getCurrentFyYear(): number {
  const now = new Date();
  const calMonth = now.getMonth() + 1;
  const calYear = now.getFullYear();
  return calMonth >= 7 ? calYear + 1 : calYear;
}

const fmt = (v: number) =>
  new Intl.NumberFormat("en-AU", { maximumFractionDigits: 0 }).format(v / 1000);

const fmtFull = (v: number) =>
  new Intl.NumberFormat("en-AU", { maximumFractionDigits: 0 }).format(v);

export default function TimeSeries() {
  const { dataPreparedToFyYear, dataPreparedToFyMonth } = usePeriodStore();
  const { includeAasb16 } = useAppStore();

  const [selectedMetrics, setSelectedMetrics] = useState<Set<Metric>>(new Set(["revenue"]));
  const [viewMode, setViewMode] = useState<ViewMode>("both");
  const [showRolling3m, setShowRolling3m] = useState(false);
  const [showRolling12m, setShowRolling12m] = useState(false);
  const [showPriorYear, setShowPriorYear] = useState(false);
  const [entityFilter, setEntityFilter] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);

  const currentFyYear = useMemo(() => getCurrentFyYear(), []);

  // FIX(L16): fetch entities from API instead of hardcoded list
  const { data: entities } = useQuery<EntityRead[]>({
    queryKey: ["entities"],
    queryFn: async () => (await api.get("/api/v1/entities")).data,
  });

  const defaultFromFy = dataPreparedToFyMonth <= 12 ? dataPreparedToFyYear - 2 : dataPreparedToFyYear - 1;
  const [fromFyYear, setFromFyYear] = useState(defaultFromFy);
  const [fromFyMonth, setFromFyMonth] = useState(dataPreparedToFyMonth);
  const [toFyYear, setToFyYear] = useState(dataPreparedToFyYear);
  const [toFyMonth, setToFyMonth] = useState(dataPreparedToFyMonth);

  const toggleMetric = (m: Metric) => {
    setSelectedMetrics((prev) => {
      const next = new Set(prev);
      if (next.has(m)) {
        if (next.size > 1) next.delete(m);
      } else {
        next.add(m);
      }
      return next;
    });
  };

  const toggleEntity = (id: string) => {
    setEntityFilter((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const metricsArray = useMemo(() => Array.from(selectedMetrics), [selectedMetrics]);
  const primaryMetric = metricsArray[0];

  // Single metric query (for table with rolling averages, prior year)
  const { data: singleData, isLoading: singleLoading } = useQuery<TimeSeriesPoint[]>({
    queryKey: ["analytics-ts-single", primaryMetric, fromFyYear, fromFyMonth, toFyYear, toFyMonth, Array.from(entityFilter).sort().join(","), includeAasb16],
    queryFn: async () => {
      const params: Record<string, string | number | boolean> = {
        metric: primaryMetric,
        from_fy_year: fromFyYear,
        from_fy_month: fromFyMonth,
        to_fy_year: toFyYear,
        to_fy_month: toFyMonth,
        include_aasb16: includeAasb16,
      };
      if (entityFilter.size > 0) {
        params.entity_ids = Array.from(entityFilter).join(",");
      }
      const res = await api.get("/api/v1/analytics/timeseries", { params });
      return res.data;
    },
  });

  // Multi metric query (for chart with multiple lines)
  const { data: multiData, isLoading: multiLoading } = useQuery<MultiTimeSeriesResponse>({
    queryKey: ["analytics-ts-multi", metricsArray.join(","), fromFyYear, fromFyMonth, toFyYear, toFyMonth, Array.from(entityFilter).sort().join(","), includeAasb16],
    queryFn: async () => {
      const params: Record<string, string | number | boolean> = {
        metrics: metricsArray.join(","),
        from_fy_year: fromFyYear,
        from_fy_month: fromFyMonth,
        to_fy_year: toFyYear,
        to_fy_month: toFyMonth,
        include_aasb16: includeAasb16,
      };
      if (entityFilter.size > 0) {
        params.entity_ids = Array.from(entityFilter).join(",");
      }
      const res = await api.get("/api/v1/analytics/timeseries/multi", { params });
      return res.data;
    },
    enabled: metricsArray.length > 0,
  });

  // Transform multi data into chart format
  // FIX(M33): align chart data by period label instead of array index
  const chartData = useMemo(() => {
    if (!multiData) return [];
    const singleByLabel = new Map<string, TimeSeriesPoint>();
    if (singleData) {
      for (const pt of singleData) {
        singleByLabel.set(pt.period_label, pt);
      }
    }
    return multiData.periods.map((label, idx) => {
      const point: Record<string, string | number> = { period: label };
      multiData.series.forEach((s) => {
        point[s.metric] = s.values[idx];
      });
      const singlePoint = singleByLabel.get(label);
      if (singlePoint) {
        point[`${primaryMetric}_prior`] = singlePoint.prior_year_value ?? 0;
        point[`${primaryMetric}_r3m`] = singlePoint.rolling_3m_avg ?? 0;
        point[`${primaryMetric}_r12m`] = singlePoint.rolling_12m_avg ?? 0;
      }
      return point;
    });
  }, [multiData, singleData, primaryMetric]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const res = await api.post(
        "/api/v1/analytics/export",
        {
          report_type: "timeseries",
          params: {
            metric: primaryMetric,
            from_fy_year: fromFyYear,
            from_fy_month: fromFyMonth,
            to_fy_year: toFyYear,
            to_fy_month: toFyMonth,
          },
          format: "xlsx",
        },
        { responseType: "blob" }
      );
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "kip_analytics_timeseries.xlsx");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [primaryMetric, fromFyYear, fromFyMonth, toFyYear, toFyMonth]);

  const isLoading = singleLoading || multiLoading;

  const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ dataKey: string; value: number; color: string }>; label?: string }) => {
    if (!active || !payload?.length) return null;
    const singlePoint = singleData?.find((p) => p.period_label === label);
    return (
      <div className="rounded-lg border bg-card p-3 shadow-md">
        <p className="mb-1 text-sm font-semibold">{label}</p>
        {payload.map((entry) => {
          const metricKey = entry.dataKey.replace("_prior", "").replace("_r3m", "").replace("_r12m", "") as Metric;
          const config = METRIC_CONFIG[metricKey];
          if (!config) return null;
          const suffix = entry.dataKey.includes("_prior")
            ? " (Prior Year)"
            : entry.dataKey.includes("_r3m")
            ? " (3M Avg)"
            : entry.dataKey.includes("_r12m")
            ? " (12M Avg)"
            : "";
          return (
            <p key={entry.dataKey} className="text-sm" style={{ color: entry.color }}>
              {config.label}{suffix}: ${fmtFull(entry.value)}
            </p>
          );
        })}
        {singlePoint?.mom_change_pct != null && (
          <p className="mt-1 text-xs text-muted-foreground">
            MoM: {singlePoint.mom_change_pct > 0 ? "+" : ""}
            {singlePoint.mom_change_pct.toFixed(1)}%
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Time Series Analysis</h1>
          <p className="text-muted-foreground">Monthly trend analysis across key financial metrics</p>
        </div>
        <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
          {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
          Export Excel
        </Button>
      </div>

      {/* Controls bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border bg-card p-4">
        {/* Metric toggles */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Metrics</label>
          <div className="flex gap-1">
            {(Object.entries(METRIC_CONFIG) as [Metric, typeof METRIC_CONFIG.revenue][]).map(([key, cfg]) => (
              <button
                key={key}
                onClick={() => toggleMetric(key)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  selectedMetrics.has(key)
                    ? "text-white"
                    : "border bg-background text-muted-foreground hover:bg-accent"
                }`}
                style={selectedMetrics.has(key) ? { backgroundColor: cfg.color } : undefined}
              >
                {cfg.label}
              </button>
            ))}
          </div>
        </div>

        {/* Date range */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">From</label>
          <div className="flex gap-1">
            <select
              value={fromFyYear}
              onChange={(e) => setFromFyYear(Number(e.target.value))}
              className="rounded-md border bg-background px-2 py-1.5 text-xs"
            >
              {Array.from({ length: 6 }, (_, i) => currentFyYear - 4 + i).map((y) => (
                <option key={y} value={y}>FY{y}</option>
              ))}
            </select>
            <select
              value={fromFyMonth}
              onChange={(e) => setFromFyMonth(Number(e.target.value))}
              className="rounded-md border bg-background px-2 py-1.5 text-xs"
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>M{String(m).padStart(2, "0")}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">To</label>
          <div className="flex gap-1">
            <select
              value={toFyYear}
              onChange={(e) => setToFyYear(Number(e.target.value))}
              className="rounded-md border bg-background px-2 py-1.5 text-xs"
            >
              {Array.from({ length: 6 }, (_, i) => currentFyYear - 4 + i).map((y) => (
                <option key={y} value={y}>FY{y}</option>
              ))}
            </select>
            <select
              value={toFyMonth}
              onChange={(e) => setToFyMonth(Number(e.target.value))}
              className="rounded-md border bg-background px-2 py-1.5 text-xs"
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>M{String(m).padStart(2, "0")}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Entity filter */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Entity</label>
          <div className="flex gap-1">
            <button
              onClick={() => setEntityFilter(new Set())}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                entityFilter.size === 0
                  ? "bg-primary text-primary-foreground"
                  : "border bg-background text-muted-foreground hover:bg-accent"
              }`}
            >
              All
            </button>
            {entities?.map((e) => (
              <button
                key={e.id}
                onClick={() => toggleEntity(e.id)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  entityFilter.has(e.id)
                    ? "bg-primary text-primary-foreground"
                    : "border bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {e.code}
              </button>
            ))}
          </div>
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
                  viewMode === mode
                    ? "bg-primary text-primary-foreground"
                    : "border bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        {/* Overlay toggles */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Overlays</label>
          <div className="flex gap-2">
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={showRolling3m}
                onChange={(e) => setShowRolling3m(e.target.checked)}
                className="rounded"
              />
              3M Avg
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={showRolling12m}
                onChange={(e) => setShowRolling12m(e.target.checked)}
                className="rounded"
              />
              12M Avg
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={showPriorYear}
                onChange={(e) => setShowPriorYear(e.target.checked)}
                className="rounded"
              />
              Prior Year
            </label>
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Chart */}
      {!isLoading && (viewMode === "chart" || viewMode === "both") && chartData.length > 0 && (
        <div className="rounded-lg border bg-card p-4">
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis
                dataKey="period"
                tick={{ fontSize: 11 }}
                interval={Math.max(0, Math.floor(chartData.length / 12) - 1)}
              />
              <YAxis
                tickFormatter={(v: number) => `$${fmt(v)}`}
                tick={{ fontSize: 11 }}
                width={80}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <ReferenceLine y={0} stroke="#888" strokeDasharray="3 3" />

              {metricsArray.map((m) => (
                <Line
                  key={m}
                  type="monotone"
                  dataKey={m}
                  name={METRIC_CONFIG[m].label}
                  stroke={METRIC_CONFIG[m].color}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
              ))}

              {showPriorYear && (
                <Line
                  type="monotone"
                  dataKey={`${primaryMetric}_prior`}
                  name={`${METRIC_CONFIG[primaryMetric].label} (Prior Year)`}
                  stroke={METRIC_CONFIG[primaryMetric].priorColor}
                  strokeWidth={1.5}
                  strokeDasharray="5 5"
                  dot={false}
                />
              )}

              {showRolling3m && (
                <Line
                  type="monotone"
                  dataKey={`${primaryMetric}_r3m`}
                  name="Rolling 3M Avg"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                />
              )}

              {showRolling12m && (
                <Line
                  type="monotone"
                  dataKey={`${primaryMetric}_r12m`}
                  name="Rolling 12M Avg"
                  stroke="#ef4444"
                  strokeWidth={1.5}
                  strokeDasharray="8 4"
                  dot={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      {!isLoading && (viewMode === "table" || viewMode === "both") && singleData && singleData.length > 0 && (
        <div className="rounded-lg border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium">Period</th>
                  {metricsArray.map((m) => (
                    <th key={m} className="px-4 py-3 text-right font-medium">{METRIC_CONFIG[m].label}</th>
                  ))}
                  <th className="px-4 py-3 text-right font-medium">MoM %</th>
                  <th className="px-4 py-3 text-right font-medium">Rolling 3M</th>
                  <th className="px-4 py-3 text-right font-medium">Rolling 12M</th>
                  <th className="px-4 py-3 text-right font-medium">vs Prior Year %</th>
                </tr>
              </thead>
              <tbody>
                {singleData.map((pt, idx) => {
                  const momHighlight =
                    pt.mom_change_pct != null && Math.abs(pt.mom_change_pct) > 10;
                  const vsPrior =
                    pt.prior_year_value != null && pt.prior_year_value !== 0
                      ? ((pt.value - pt.prior_year_value) / Math.abs(pt.prior_year_value)) * 100
                      : null;
                  return (
                    <tr
                      key={idx}
                      className={`border-b transition-colors hover:bg-muted/30 ${
                        momHighlight ? "bg-amber-50 dark:bg-amber-950/20" : ""
                      }`}
                    >
                      <td className="px-4 py-2.5 font-medium">{pt.period_label}</td>
                      {metricsArray.map((m) => {
                        const val = m === primaryMetric ? pt.value : (multiData?.series.find((s) => s.metric === m)?.values[idx] ?? 0);
                        return (
                          <td key={m} className="px-4 py-2.5 text-right tabular-nums">
                            ${fmtFull(val)}
                          </td>
                        );
                      })}
                      <td
                        className={`px-4 py-2.5 text-right tabular-nums ${
                          pt.mom_change_pct != null
                            ? pt.mom_change_pct > 0
                              ? "text-emerald-600"
                              : pt.mom_change_pct < 0
                              ? "text-red-600"
                              : ""
                            : ""
                        }`}
                      >
                        {pt.mom_change_pct != null
                          ? `${pt.mom_change_pct > 0 ? "+" : ""}${pt.mom_change_pct.toFixed(1)}%`
                          : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {pt.rolling_3m_avg != null ? `$${fmtFull(pt.rolling_3m_avg)}` : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {pt.rolling_12m_avg != null ? `$${fmtFull(pt.rolling_12m_avg)}` : "—"}
                      </td>
                      <td
                        className={`px-4 py-2.5 text-right tabular-nums ${
                          vsPrior != null
                            ? vsPrior > 0
                              ? "text-emerald-600"
                              : vsPrior < 0
                              ? "text-red-600"
                              : ""
                            : ""
                        }`}
                      >
                        {vsPrior != null
                          ? `${vsPrior > 0 ? "+" : ""}${vsPrior.toFixed(1)}%`
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!isLoading && (!singleData || singleData.length === 0) && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No data available for the selected period and filters.
        </div>
      )}
    </div>
  );
}
