import { useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Percent,
  BarChart3,
  Landmark,
  CreditCard,
  RefreshCw,
  Loader2,
  AlertTriangle,
  FileSpreadsheet,
  X,
  Download,
} from "lucide-react";
import api from "@/utils/api";
import { usePeriodStore } from "@/stores/period";
import { useAppStore } from "@/stores/app";
import FinancialTable from "@/components/FinancialTable";
import type {
  DashboardKPIs,
  FinancialStatementResponse,
  FinancialRow,
  TimeSeriesPoint,
  LocationPerformanceRow,
  EntityRead,
} from "@/types/api";

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `-$${formatted}` : `$${formatted}`;
}

function fmtK(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(Math.round(n));
}

function fmtPct(n: number | null): string {
  if (n === null) return "—";
  return `${n.toFixed(1)}%`;
}

function variancePct(current: number, prior: number): string | null {
  if (!prior) return null;
  const pct = ((current - prior) / Math.abs(prior)) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

const SUMMARY_CODES = new Set(["REV-SALES", "GM", "EBITDA", "NPAT"]);

function filterSummaryRows(rows: FinancialRow[]): FinancialRow[] {
  return rows.filter((r) => SUMMARY_CODES.has(r.account_code));
}

function trailingRange(fyYear: number, fyMonth: number, months: number) {
  let fromMonth = fyMonth - (months - 1);
  let fromYear = fyYear;
  while (fromMonth <= 0) {
    fromMonth += 12;
    fromYear -= 1;
  }
  return { fromFyYear: fromYear, fromFyMonth: fromMonth, toFyYear: fyYear, toFyMonth: fyMonth };
}

interface PackVersion {
  id: string;
  name: string;
  fy_year: number;
  status: string;
}

function ManagementPackModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { fyYear, fyMonth } = usePeriodStore();
  const { includeAasb16 } = useAppStore();
  const [entityId, setEntityId] = useState<string>("");
  const [aasb16, setAasb16] = useState(includeAasb16);
  const [versionId, setVersionId] = useState<string>("");

  const entities = useQuery<EntityRead[]>({
    queryKey: ["entities-pack"],
    queryFn: async () => (await api.get("/api/v1/entities/")).data,
    enabled: open,
  });

  const versions = useQuery<PackVersion[]>({
    queryKey: ["pack-versions"],
    queryFn: async () => (await api.get("/api/v1/reports/management-pack/versions")).data,
    enabled: open,
  });

  const download = useMutation({
    mutationFn: async () => {
      const res = await api.post(
        "/api/v1/reports/management-pack",
        {
          entity_id: entityId || null,
          include_aasb16: aasb16,
          periods: {
            prior2_fy_year: fyYear - 2,
            prior1_fy_year: fyYear - 1,
            ytd_fy_year: fyYear,
            ytd_to_month: fyMonth,
            forecast_fy_year: fyYear,
            budget_version_id: versionId || null,
          },
        },
        { responseType: "blob" },
      );
      const blob = new Blob([res.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match?.[1] || `KipGroup_ManagementPack.xlsx`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
  });

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold">Management Pack Export</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Entity</label>
            <select
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            >
              <option value="">All (Consolidated)</option>
              {entities.data?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.code} — {e.name || e.code}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">AASB16 Treatment</label>
            <select
              value={aasb16 ? "statutory" : "exlease"}
              onChange={(e) => setAasb16(e.target.value === "statutory")}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            >
              <option value="statutory">Statutory (incl. leases)</option>
              <option value="exlease">Ex-lease</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Budget Version</label>
            <select
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            >
              <option value="">Auto-detect</option>
              {versions.data?.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} (FY{v.fy_year} — {v.status})
                </option>
              ))}
            </select>
          </div>

          <div className="rounded-md border bg-muted/50 p-3 text-xs text-muted-foreground">
            <p>
              Exports FY{fyYear - 2}, FY{fyYear - 1}, FY{fyYear} YTD to M
              {String(fyMonth).padStart(2, "0")}, and FYE estimate.
              {!entityId && " Includes per-entity IS/BS breakdown sheets."}
            </p>
          </div>

          {download.isError && (
            <p className="text-sm text-destructive">
              Export failed. Check console for details.
            </p>
          )}

          <button
            onClick={() => download.mutate()}
            disabled={download.isPending}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-[#1F3D6E] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#2a5090] disabled:opacity-50"
          >
            {download.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {download.isPending ? "Generating..." : "Download Management Pack"}
          </button>
        </div>
      </div>
    </div>
  );
}


export default function Dashboard() {
  const { fyYear, fyMonth } = usePeriodStore();
  const [packOpen, setPackOpen] = useState(false);

  const kpis = useQuery<DashboardKPIs>({
    queryKey: ["dashboard-kpis", fyYear, fyMonth],
    queryFn: async () => {
      const res = await api.get("/api/v1/dashboard/kpis", {
        params: { fy_year: fyYear, fy_month: fyMonth },
      });
      return res.data;
    },
  });

  const fullIS = useQuery<FinancialStatementResponse>({
    queryKey: ["consolidated-is-full", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/consolidated/is", {
        params: { fy_year: fyYear },
      });
      return res.data;
    },
  });

  const trailing = trailingRange(fyYear, fyMonth, 12);

  const revenueTrend = useQuery<TimeSeriesPoint[]>({
    queryKey: ["dash-revenue-trend", trailing.fromFyYear, trailing.fromFyMonth, trailing.toFyYear, trailing.toFyMonth],
    queryFn: async () => {
      const res = await api.get("/api/v1/analytics/timeseries", {
        params: {
          metric: "revenue",
          from_fy_year: trailing.fromFyYear,
          from_fy_month: trailing.fromFyMonth,
          to_fy_year: trailing.toFyYear,
          to_fy_month: trailing.toFyMonth,
        },
      });
      return res.data;
    },
  });

  const locations = useQuery<LocationPerformanceRow[]>({
    queryKey: ["dash-locations", fyYear, fyMonth],
    queryFn: async () => {
      const res = await api.get("/api/v1/analytics/locations", {
        params: { fy_year: fyYear, fy_month: fyMonth },
      });
      return res.data;
    },
  });

  const k = kpis.data;
  const lastSyncStale =
    k?.last_sync_at &&
    Date.now() - new Date(k.last_sync_at).getTime() > 25 * 3_600_000;

  let condensedPeriods: string[] = [];
  let condensedRows: FinancialRow[] = [];
  if (fullIS.data) {
    const allPeriods = fullIS.data.periods;
    const available = allPeriods.slice(0, fyMonth);
    condensedPeriods = available.slice(-6);
    const summary = filterSummaryRows(fullIS.data.rows);
    condensedRows = summary.map((row) => ({
      ...row,
      values: Object.fromEntries(condensedPeriods.map((p) => [p, row.values[p] ?? 0])),
      entity_breakdown: {},
    }));
  }

  const waterfallData = useMemo(() => {
    if (!fullIS.data) return [];
    const summary = filterSummaryRows(fullIS.data.rows);
    const currentPeriod = fullIS.data.periods[fyMonth - 1];
    if (!currentPeriod) return [];

    const labels: Record<string, string> = {
      "REV-SALES": "Revenue",
      "GM": "Gross Margin",
      "EBITDA": "EBITDA",
      "NPAT": "NPAT",
    };
    const colors: Record<string, string> = {
      "REV-SALES": "#2563eb",
      "GM": "#16a34a",
      "EBITDA": "#9333ea",
      "NPAT": "#ea580c",
    };
    return ["REV-SALES", "GM", "EBITDA", "NPAT"]
      .map((code) => {
        const row = summary.find((r) => r.account_code === code);
        return {
          name: labels[code],
          value: row?.values[currentPeriod] ?? 0,
          fill: colors[code],
        };
      });
  }, [fullIS.data, fyMonth]);

  const topSites = useMemo(() => {
    if (!locations.data) return [];
    return locations.data
      .sort((a, b) => b.site_pl - a.site_pl)
      .slice(0, 10)
      .map((loc) => ({
        name: (loc.location_name ?? loc.location_code ?? "Unknown").replace(/^Kip\s+/i, ""),
        revenue: loc.revenue,
        costs: loc.direct_costs,
        sitePL: loc.site_pl,
      }));
  }, [locations.data]);

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            FY{fyYear} &middot; M{String(fyMonth).padStart(2, "0")} overview
          </p>
        </div>
        <button
          onClick={() => setPackOpen(true)}
          className="flex items-center gap-2 rounded-md bg-[#1F3D6E] px-4 py-2 text-sm font-medium text-white hover:bg-[#2a5090]"
        >
          <FileSpreadsheet className="h-4 w-4" />
          Management Pack
        </button>
      </div>

      <ManagementPackModal open={packOpen} onClose={() => setPackOpen(false)} />

      {kpis.isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {kpis.isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load KPIs.
        </div>
      )}

      {k && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <KpiTile
            title="Revenue MTD"
            value={fmtAUD(k.revenue_mtd)}
            sub={
              variancePct(k.revenue_mtd, k.revenue_pcp)
                ? `vs PY: ${variancePct(k.revenue_mtd, k.revenue_pcp)}`
                : "No PY data"
            }
            icon={DollarSign}
            trend={k.revenue_mtd >= k.revenue_pcp ? "up" : "down"}
          />
          <KpiTile
            title="Gross Margin %"
            value={fmtPct(k.gm_pct)}
            sub={k.gm_pct_pcp !== null ? `PY: ${fmtPct(k.gm_pct_pcp)}` : "No PY data"}
            icon={Percent}
            trend={
              k.gm_pct !== null && k.gm_pct_pcp !== null
                ? k.gm_pct >= k.gm_pct_pcp
                  ? "up"
                  : "down"
                : null
            }
          />
          <KpiTile
            title="EBITDA"
            value={fmtAUD(k.ebitda_mtd)}
            sub={`YTD: ${fmtAUD(k.ebitda_ytd)}`}
            icon={BarChart3}
            trend={k.ebitda_mtd >= 0 ? "up" : "down"}
          />
          <KpiTile
            title="Net Cash"
            value={fmtAUD(k.net_cash)}
            sub="Latest BS balance"
            icon={Landmark}
            trend={k.net_cash >= 0 ? "up" : "down"}
          />
          <KpiTile
            title="Total Debt"
            value={fmtAUD(Math.abs(k.total_debt))}
            sub="All facility closing balances"
            icon={CreditCard}
            trend={null}
          />
          <KpiTile
            title="Sync Status"
            value={
              k.last_sync_at
                ? new Date(k.last_sync_at).toLocaleString("en-AU", {
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "No syncs"
            }
            sub={lastSyncStale ? "Stale — >25 hours" : "Up to date"}
            icon={lastSyncStale ? AlertTriangle : RefreshCw}
            trend={lastSyncStale ? "down" : "up"}
          />
        </div>
      )}

      {/* Charts row: Revenue Trend + P&L Cascade */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Revenue vs Prior Year */}
        <div className="rounded-lg border bg-card p-5">
          <h2 className="text-lg font-semibold mb-1">Revenue — Trailing 12 Months</h2>
          <p className="text-xs text-muted-foreground mb-4">Current year vs prior year</p>
          {revenueTrend.isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : revenueTrend.data && revenueTrend.data.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={revenueTrend.data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="period_label" tick={{ fontSize: 10 }} interval={0} angle={-45} textAnchor="end" height={50} />
                <YAxis tickFormatter={(v: number) => `$${fmtK(v)}`} tick={{ fontSize: 10 }} width={65} />
                <Tooltip content={<RevenueTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="prior_year_value" name="Prior Year" fill="#cbd5e1" radius={[2, 2, 0, 0]} />
                <Bar dataKey="value" name="Current Year" fill="#2563eb" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-16 text-center text-sm text-muted-foreground">No revenue data available.</p>
          )}
        </div>

        {/* P&L Cascade — current month */}
        <div className="rounded-lg border bg-card p-5">
          <h2 className="text-lg font-semibold mb-1">P&L Cascade — Current Month</h2>
          <p className="text-xs text-muted-foreground mb-4">Revenue through to NPAT</p>
          {fullIS.isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : waterfallData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={waterfallData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v: number) => `$${fmtK(v)}`} tick={{ fontSize: 10 }} width={65} />
                <Tooltip
                  formatter={(value: number) => [`$${Math.round(value).toLocaleString("en-AU")}`, ""]}
                  labelStyle={{ fontWeight: 600 }}
                  contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }}
                />
                <ReferenceLine y={0} stroke="#94a3b8" />
                <Bar dataKey="value" name="Amount" radius={[4, 4, 0, 0]}>
                  {waterfallData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-16 text-center text-sm text-muted-foreground">No P&L data for current month.</p>
          )}
        </div>
      </div>

      {/* Top 10 Sites */}
      <div className="rounded-lg border bg-card p-5">
        <h2 className="text-lg font-semibold mb-1">Top 10 Sites — Site P&L</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Revenue and direct costs for M{String(fyMonth).padStart(2, "0")}
        </p>
        {locations.isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : topSites.length > 0 ? (
          <ResponsiveContainer width="100%" height={Math.max(300, topSites.length * 40 + 40)}>
            <BarChart data={topSites} layout="vertical" margin={{ top: 5, right: 30, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" horizontal={false} />
              <XAxis type="number" tickFormatter={(v: number) => `$${fmtK(v)}`} tick={{ fontSize: 10 }} />
              <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, name: string) => [
                  `$${Math.round(value).toLocaleString("en-AU")}`,
                  name === "revenue" ? "Revenue" : name === "costs" ? "Direct Costs" : "Site P&L",
                ]}
                contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="revenue" name="Revenue" fill="#2563eb" radius={[0, 4, 4, 0]} stackId="a" />
              <Bar dataKey="costs" name="Direct Costs" fill="#f87171" radius={[0, 4, 4, 0]} stackId="b" />
              <Bar dataKey="sitePL" name="Site P&L" fill="#16a34a" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-12 text-center text-sm text-muted-foreground">No location data available for this period.</p>
        )}
      </div>

      {/* Condensed P&L — trailing months */}
      {condensedRows.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">
            P&L Summary — Last {condensedPeriods.length} Months
          </h2>
          <FinancialTable
            rows={condensedRows}
            periods={condensedPeriods}
            compact
            highlightVariance
          />
        </div>
      )}

      {fullIS.isLoading && !kpis.isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}
    </div>
  );
}


// ── Revenue Tooltip ─────────────────────────────────────────────────────

function RevenueTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ dataKey: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const current = payload.find((p) => p.dataKey === "value");
  const prior = payload.find((p) => p.dataKey === "prior_year_value");
  const growth =
    current && prior && prior.value
      ? ((current.value - prior.value) / Math.abs(prior.value)) * 100
      : null;

  return (
    <div className="rounded-lg border bg-card p-3 shadow-md text-sm">
      <p className="font-semibold mb-1">{label}</p>
      {current && (
        <p style={{ color: "#2563eb" }}>
          Current: ${Math.round(current.value).toLocaleString("en-AU")}
        </p>
      )}
      {prior && prior.value != null && (
        <p style={{ color: "#94a3b8" }}>
          Prior Year: ${Math.round(prior.value).toLocaleString("en-AU")}
        </p>
      )}
      {growth != null && (
        <p className={`mt-1 text-xs font-medium ${growth >= 0 ? "text-emerald-600" : "text-red-600"}`}>
          {growth >= 0 ? "+" : ""}{growth.toFixed(1)}% YoY
        </p>
      )}
    </div>
  );
}


// ── KPI Tile ────────────────────────────────────────────────────────────

interface KpiTileProps {
  title: string;
  value: string;
  sub: string;
  icon: React.ElementType;
  trend: "up" | "down" | null;
}

function KpiTile({ title, value, sub, icon: Icon, trend }: KpiTileProps) {
  const TrendIcon =
    trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : null;
  const trendColor =
    trend === "up"
      ? "text-emerald-600"
      : trend === "down"
        ? "text-red-600"
        : "text-muted-foreground";

  return (
    <div className="rounded-lg border bg-card p-5 transition-colors hover:border-primary/20">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-muted-foreground">{title}</span>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      <div className={`mt-1 flex items-center gap-1 text-xs ${trendColor}`}>
        {TrendIcon && <TrendIcon className="h-3 w-3" />}
        <span>{sub}</span>
      </div>
    </div>
  );
}
