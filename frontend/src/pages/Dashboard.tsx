import { useQuery } from "@tanstack/react-query";
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
} from "lucide-react";
import api from "@/utils/api";
import { usePeriodStore } from "@/stores/period";
import FinancialTable from "@/components/FinancialTable";
import type { DashboardKPIs, FinancialStatementResponse, FinancialRow } from "@/types/api";

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `-$${formatted}` : `$${formatted}`;
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

export default function Dashboard() {
  const { fyYear, fyMonth } = usePeriodStore();

  const kpis = useQuery<DashboardKPIs>({
    queryKey: ["dashboard-kpis", fyYear, fyMonth],
    queryFn: async () => {
      const res = await api.get("/api/v1/dashboard/kpis", {
        params: { fy_year: fyYear, fy_month: fyMonth },
      });
      return res.data;
    },
  });

  // Fetch full year IS for the condensed trailing-6-month P&L
  const fullIS = useQuery<FinancialStatementResponse>({
    queryKey: ["consolidated-is-full", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/consolidated/is", {
        params: { fy_year: fyYear },
      });
      return res.data;
    },
  });

  const k = kpis.data;
  const lastSyncStale =
    k?.last_sync_at &&
    Date.now() - new Date(k.last_sync_at).getTime() > 25 * 3_600_000;

  // Build condensed table: last 6 months of full-year data
  let condensedPeriods: string[] = [];
  let condensedRows: FinancialRow[] = [];
  if (fullIS.data) {
    const allPeriods = fullIS.data.periods;
    // Take up to the current fy_month (0-indexed: take first fyMonth items), then last 6
    const available = allPeriods.slice(0, fyMonth);
    condensedPeriods = available.slice(-6);
    const summary = filterSummaryRows(fullIS.data.rows);
    condensedRows = summary.map((row) => ({
      ...row,
      values: Object.fromEntries(condensedPeriods.map((p) => [p, row.values[p] ?? 0])),
      entity_breakdown: {},
    }));
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          FY{fyYear} &middot; M{String(fyMonth).padStart(2, "0")} overview
        </p>
      </div>

      {/* KPI Tiles */}
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
