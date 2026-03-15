import { useState, useCallback, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  ChevronRight,
  Save,
  Building2,
  TrendingDown,
  DollarSign,
  Landmark,
  X,
  ArrowDownRight,
  ArrowUpRight,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  DebtSummary,
  DebtFacilityRead,
  DebtFacilityUpdate,
  BudgetVersion,
} from "@/types/api";

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
}

function fmtAUDk(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return fmtAUD(n);
}

function fmtRate(n: number | null): string {
  if (n == null) return "-";
  return `${(n * 100).toFixed(2)}%`;
}

const FACILITY_TYPE_LABELS: Record<string, string> = {
  property_loan: "Property Loan",
  equipment_loan: "Equipment Loan",
  vehicle_loan: "Vehicle Loan",
  revolving: "Revolving",
  overdraft: "Overdraft",
};

const FACILITY_TYPE_COLORS: Record<string, string> = {
  property_loan: "#6366f1",
  equipment_loan: "#8b5cf6",
  vehicle_loan: "#a78bfa",
  revolving: "#c4b5fd",
  overdraft: "#ddd6fe",
};

const CHART_COLORS = [
  "#6366f1", "#8b5cf6", "#ec4899", "#f43f5e",
  "#f97316", "#eab308", "#22c55e", "#06b6d4",
];

export default function DebtSchedulePage() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();
  const [selectedFacility, setSelectedFacility] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, Partial<DebtFacilityUpdate>>>({});

  const isAdmin = user?.role === "admin";

  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const { data: debtData, isLoading, error, refetch } = useQuery<DebtSummary>({
    queryKey: ["debt-facilities", activeVersionId],
    queryFn: async () => {
      const res = await api.get(`/api/v1/budgets/${activeVersionId}/debt`);
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  const updateMutation = useMutation({
    mutationFn: async ({
      facilityId,
      payload,
    }: {
      facilityId: string;
      payload: DebtFacilityUpdate;
    }) => {
      await api.put(
        `/api/v1/budgets/${activeVersionId}/debt/facilities/${facilityId}`,
        payload
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["debt-facilities", activeVersionId],
      });
    },
  });

  const handleSaveFacility = useCallback(
    (facilityId: string, fac: DebtFacilityRead) => {
      const editsForFac = edits[facilityId] ?? {};
      const payload: DebtFacilityUpdate = {
        base_rate: editsForFac.base_rate ?? fac.base_rate,
        margin: editsForFac.margin ?? fac.margin,
        monthly_repayment: editsForFac.monthly_repayment ?? fac.monthly_repayment,
      };
      updateMutation.mutate({ facilityId, payload });
      setEdits((prev) => {
        const next = { ...prev };
        delete next[facilityId];
        return next;
      });
    },
    [edits, updateMutation]
  );

  const activeVersion = versions?.find((v) => v.id === activeVersionId);
  const facilities = debtData?.facilities ?? [];
  const selectedFac = facilities.find((f) => f.id === selectedFacility);

  // Build stacked area chart data from individual facility histories
  const stackedChartData = useMemo(() => {
    if (!debtData?.total_debt_history?.length) return [];
    const periodMap = new Map<string, Record<string, number>>();

    for (const point of debtData.total_debt_history) {
      periodMap.set(point.period_label, { period: 0 });
    }

    for (const fac of facilities) {
      for (const h of fac.history) {
        const entry = periodMap.get(h.period_label);
        if (entry) {
          entry[fac.code] = h.balance;
        }
      }
    }

    return Array.from(periodMap.entries()).map(([label, vals]) => ({
      period: label,
      ...vals,
    }));
  }, [debtData, facilities]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Debt Schedule</h1>
        <p className="text-muted-foreground">
          FY{fyYear}
          {activeVersion && <> &middot; {activeVersion.name}</>}
        </p>
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

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Failed to load debt facilities.</p>
          <Button variant="outline" size="sm" className="mt-2" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      )}

      {debtData && facilities.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No debt accounts found on the balance sheet. Ensure consolidation has run and BS-DEBT-* accounts have balances.
        </div>
      )}

      {debtData && facilities.length > 0 && (
        <>
          {/* ── Summary Cards ─────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <SummaryCard
              icon={<Landmark className="h-4 w-4" />}
              label="Total Debt"
              value={fmtAUDk(debtData.total_debt)}
              sub={`${debtData.facility_count} facilities`}
            />
            <SummaryCard
              icon={<DollarSign className="h-4 w-4" />}
              label="Budget Interest"
              value={fmtAUDk(debtData.total_interest_budget)}
              sub="FY total"
            />
            <SummaryCard
              icon={<TrendingDown className="h-4 w-4" />}
              label="Budget Repayments"
              value={fmtAUDk(debtData.total_repayment_budget)}
              sub="FY total"
            />
            <SummaryCard
              icon={<Building2 className="h-4 w-4" />}
              label="Avg Monthly Repay"
              value={fmtAUDk(
                facilities.reduce((s, f) => s + (f.avg_monthly_repayment ?? 0), 0) /
                  Math.max(facilities.filter((f) => f.avg_monthly_repayment).length, 1)
              )}
              sub="Implied from actuals"
            />
          </div>

          {/* ── Stacked Area Chart ────────────────────────────────── */}
          {stackedChartData.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Debt Balance Over Time</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={stackedChartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="period"
                      tick={{ fontSize: 11 }}
                      stroke="hsl(var(--muted-foreground))"
                    />
                    <YAxis
                      tickFormatter={(v: number) => fmtAUDk(v)}
                      tick={{ fontSize: 11 }}
                      stroke="hsl(var(--muted-foreground))"
                    />
                    <Tooltip
                      formatter={(value: number, name: string) => [
                        `$${fmtAUD(value)}`,
                        facilities.find((f) => f.code === name)?.name ?? name,
                      ]}
                      contentStyle={{
                        background: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Legend
                      formatter={(value: string) =>
                        facilities.find((f) => f.code === value)?.name ?? value
                      }
                      wrapperStyle={{ fontSize: 11 }}
                    />
                    {facilities.map((fac, i) => (
                      <Area
                        key={fac.code}
                        type="monotone"
                        dataKey={fac.code}
                        stackId="1"
                        fill={CHART_COLORS[i % CHART_COLORS.length]}
                        stroke={CHART_COLORS[i % CHART_COLORS.length]}
                        fillOpacity={0.6}
                        cursor="pointer"
                        onClick={() => setSelectedFacility(fac.id)}
                      />
                    ))}
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* ── Facility Cards ────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {facilities.map((fac, idx) => (
              <FacilityCard
                key={fac.id}
                fac={fac}
                color={CHART_COLORS[idx % CHART_COLORS.length]}
                isSelected={selectedFacility === fac.id}
                onClick={() =>
                  setSelectedFacility(selectedFacility === fac.id ? null : fac.id)
                }
              />
            ))}
          </div>

          {/* ── Selected Facility Detail Panel ────────────────────── */}
          {selectedFac && (
            <FacilityDetail
              fac={selectedFac}
              isAdmin={isAdmin}
              edits={edits[selectedFac.id] ?? {}}
              onEditField={(field, value) =>
                setEdits((prev) => ({
                  ...prev,
                  [selectedFac.id]: {
                    ...(prev[selectedFac.id] ?? {}),
                    [field]: value,
                  },
                }))
              }
              onSave={() => handleSaveFacility(selectedFac.id, selectedFac)}
              isSaving={updateMutation.isPending}
              onClose={() => setSelectedFacility(null)}
              color={
                CHART_COLORS[
                  facilities.findIndex((f) => f.id === selectedFac.id) %
                    CHART_COLORS.length
                ]
              }
            />
          )}
        </>
      )}
    </div>
  );
}

/* ── Summary Card ──────────────────────────────────────────────────── */

function SummaryCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
          {icon}
          {label}
        </div>
        <div className="text-2xl font-bold tabular-nums">${value}</div>
        <div className="text-xs text-muted-foreground mt-0.5">{sub}</div>
      </CardContent>
    </Card>
  );
}

/* ── Facility Card ─────────────────────────────────────────────────── */

function FacilityCard({
  fac,
  color,
  isSelected,
  onClick,
}: {
  fac: DebtFacilityRead;
  color: string;
  isSelected: boolean;
  onClick: () => void;
}) {
  const balance = fac.current_balance ?? fac.opening_balance;
  const lastMovement = fac.history.length > 1
    ? fac.history[fac.history.length - 1].movement
    : 0;

  return (
    <Card
      className={`cursor-pointer transition-all hover:shadow-md ${
        isSelected ? "ring-2 ring-primary" : ""
      }`}
      onClick={onClick}
    >
      <CardContent className="pt-6">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ background: color }}
              />
              <span className="font-semibold text-sm">{fac.name}</span>
            </div>
            <span className="text-xs text-muted-foreground ml-5">
              {FACILITY_TYPE_LABELS[fac.facility_type ?? ""] ?? fac.facility_type ?? "Loan"}
              {fac.entity_code && <> &middot; {fac.entity_code}</>}
            </span>
          </div>
          <ChevronRight className="h-4 w-4 text-muted-foreground mt-1 flex-shrink-0" />
        </div>

        <div className="space-y-2">
          <div className="flex justify-between items-baseline">
            <span className="text-xs text-muted-foreground">Current Balance</span>
            <span className="text-lg font-bold tabular-nums">${fmtAUD(balance)}</span>
          </div>

          <div className="flex justify-between items-center">
            <span className="text-xs text-muted-foreground">Last Movement</span>
            <span
              className={`text-xs font-medium tabular-nums flex items-center gap-1 ${
                lastMovement < 0
                  ? "text-emerald-600"
                  : lastMovement > 0
                  ? "text-red-500"
                  : "text-muted-foreground"
              }`}
            >
              {lastMovement < 0 ? (
                <ArrowDownRight className="h-3 w-3" />
              ) : lastMovement > 0 ? (
                <ArrowUpRight className="h-3 w-3" />
              ) : null}
              ${fmtAUD(lastMovement)}
            </span>
          </div>

          {fac.avg_monthly_repayment != null && fac.avg_monthly_repayment > 0 && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">Avg Monthly Repay</span>
              <span className="text-xs font-medium tabular-nums">
                ${fmtAUD(fac.avg_monthly_repayment)}
              </span>
            </div>
          )}
        </div>

        {/* Mini sparkline */}
        {fac.history.length > 2 && (
          <div className="mt-3 -mx-1">
            <ResponsiveContainer width="100%" height={40}>
              <AreaChart data={fac.history} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
                <Area
                  type="monotone"
                  dataKey="balance"
                  fill={color}
                  stroke={color}
                  fillOpacity={0.15}
                  strokeWidth={1.5}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Facility Detail Panel ─────────────────────────────────────────── */

function FacilityDetail({
  fac,
  isAdmin,
  edits,
  onEditField,
  onSave,
  isSaving,
  onClose,
  color,
}: {
  fac: DebtFacilityRead;
  isAdmin: boolean;
  edits: Partial<DebtFacilityUpdate>;
  onEditField: (field: keyof DebtFacilityUpdate, value: number | null) => void;
  onSave: () => void;
  isSaving: boolean;
  onClose: () => void;
  color: string;
}) {
  const [activeTab, setActiveTab] = useState<"history" | "schedule">("history");
  const hasPendingEdits = Object.keys(edits).length > 0;
  const totalRate =
    (edits.base_rate ?? fac.base_rate ?? 0) + (edits.margin ?? fac.margin);

  const movementChartData = useMemo(() => {
    return fac.history
      .filter((_, i) => i > 0)
      .map((h) => ({
        period: h.period_label,
        repayment: h.movement < 0 ? Math.abs(h.movement) : 0,
        drawdown: h.movement > 0 ? h.movement : 0,
      }));
  }, [fac.history]);

  return (
    <Card className="relative">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 rounded-full" style={{ background: color }} />
              <CardTitle className="text-lg">{fac.name}</CardTitle>
            </div>
            <p className="text-sm text-muted-foreground mt-1 ml-7">
              {FACILITY_TYPE_LABELS[fac.facility_type ?? ""] ?? "Loan"} &middot;{" "}
              {fac.entity_code ?? "—"} &middot; {fac.code}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* ── Key Metrics Row ──────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <MetricBox
            label="Opening Balance"
            value={`$${fmtAUD(fac.opening_balance)}`}
          />
          <MetricBox
            label="Current Balance"
            value={`$${fmtAUD(fac.current_balance ?? fac.opening_balance)}`}
          />
          <MetricBox
            label="Avg Monthly Repay"
            value={
              fac.avg_monthly_repayment
                ? `$${fmtAUD(fac.avg_monthly_repayment)}`
                : "—"
            }
            sub="Implied from actuals"
          />
          <MetricBox
            label="Interest Rate"
            value={fac.implied_interest_rate != null ? fmtRate(fac.implied_interest_rate) : "Not set"}
          />
          <MetricBox
            label="Maturity"
            value={fac.maturity_date ?? "—"}
          />
        </div>

        {/* ── Forecast Override Inputs ────────────────── */}
        {isAdmin && (
          <div className="rounded-lg border bg-muted/30 p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold">Forecast Assumptions</h4>
              {hasPendingEdits && (
                <Button
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSave();
                  }}
                  disabled={isSaving}
                >
                  {isSaving ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                  ) : (
                    <Save className="h-3.5 w-3.5 mr-1" />
                  )}
                  Save
                </Button>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-xs text-muted-foreground block mb-1">
                  Base Rate (decimal)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder={
                    fac.base_rate != null
                      ? `${(fac.base_rate * 100).toFixed(2)}%`
                      : "e.g. 0.065"
                  }
                  value={
                    edits.base_rate !== undefined
                      ? String(edits.base_rate ?? "")
                      : String(fac.base_rate ?? "")
                  }
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    onEditField("base_rate", isNaN(val) ? null : val);
                  }}
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">
                  Margin (decimal)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="e.g. 0.02"
                  value={
                    edits.margin !== undefined
                      ? String(edits.margin ?? "")
                      : String(fac.margin ?? "")
                  }
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    onEditField("margin", isNaN(val) ? null : val);
                  }}
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">
                  Monthly Repayment ($)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder={
                    fac.avg_monthly_repayment
                      ? `Implied: $${fmtAUD(fac.avg_monthly_repayment)}`
                      : "e.g. 25000"
                  }
                  value={
                    edits.monthly_repayment !== undefined
                      ? String(edits.monthly_repayment ?? "")
                      : String(fac.monthly_repayment ?? "")
                  }
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    onEditField("monthly_repayment", isNaN(val) ? null : val);
                  }}
                />
              </div>
            </div>
            {totalRate > 0 && (
              <p className="text-xs text-muted-foreground mt-2">
                All-in rate: {fmtRate(totalRate)}
              </p>
            )}
          </div>
        )}

        {/* ── Tab Bar ────────────────────────────────── */}
        <div className="flex gap-1 border-b">
          <button
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "history"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setActiveTab("history")}
          >
            Historical Balance
          </button>
          <button
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "schedule"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setActiveTab("schedule")}
          >
            Budget Schedule
          </button>
        </div>

        {/* ── History Tab ────────────────────────────── */}
        {activeTab === "history" && (
          <div className="space-y-4">
            {/* Balance chart */}
            {fac.history.length > 1 && (
              <div>
                <h4 className="text-sm font-medium mb-2 text-muted-foreground">Balance Trend</h4>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={fac.history} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="period_label" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tickFormatter={(v: number) => fmtAUDk(v)} tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                    <Tooltip
                      formatter={(v: number) => [`$${fmtAUD(v)}`, "Balance"]}
                      contentStyle={{
                        background: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="balance"
                      fill={color}
                      stroke={color}
                      fillOpacity={0.2}
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Movements chart */}
            {movementChartData.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2 text-muted-foreground">Monthly Movements</h4>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={movementChartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="period" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tickFormatter={(v: number) => fmtAUDk(v)} tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                    <Tooltip
                      formatter={(v: number, name: string) => [
                        `$${fmtAUD(v)}`,
                        name === "repayment" ? "Repayment" : "Drawdown",
                      ]}
                      contentStyle={{
                        background: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="repayment" fill="#22c55e" radius={[2, 2, 0, 0]} name="Repayment" />
                    <Bar dataKey="drawdown" fill="#ef4444" radius={[2, 2, 0, 0]} name="Drawdown" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* History table */}
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-xs">Period</th>
                    <th className="px-3 py-2 text-right font-medium text-xs">Balance</th>
                    <th className="px-3 py-2 text-right font-medium text-xs">Movement</th>
                  </tr>
                </thead>
                <tbody>
                  {fac.history.map((h, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="px-3 py-1.5 text-xs">{h.period_label}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                        ${fmtAUD(h.balance)}
                      </td>
                      <td
                        className={`px-3 py-1.5 text-right tabular-nums text-xs ${
                          h.movement < 0
                            ? "text-emerald-600"
                            : h.movement > 0
                            ? "text-red-500"
                            : "text-muted-foreground"
                        }`}
                      >
                        {i === 0 ? "—" : `$${fmtAUD(h.movement)}`}
                      </td>
                    </tr>
                  ))}
                  {fac.history.length === 0 && (
                    <tr>
                      <td colSpan={3} className="px-3 py-4 text-center text-xs text-muted-foreground">
                        No historical data available
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Schedule Tab ───────────────────────────── */}
        {activeTab === "schedule" && (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium text-xs">Period</th>
                  <th className="px-3 py-2 text-right font-medium text-xs">Opening</th>
                  <th className="px-3 py-2 text-right font-medium text-xs">Interest</th>
                  <th className="px-3 py-2 text-right font-medium text-xs">Repayment</th>
                  <th className="px-3 py-2 text-right font-medium text-xs">Closing</th>
                  <th className="px-3 py-2 text-right font-medium text-xs">Rate</th>
                </tr>
              </thead>
              <tbody>
                {fac.schedule.map((row, idx) => (
                  <tr key={idx} className="border-b last:border-0">
                    <td className="px-3 py-1.5 text-xs">{row.period_label}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                      ${fmtAUD(row.opening_balance)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs text-amber-600">
                      ${fmtAUD(row.interest_expense)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs text-emerald-600">
                      ${fmtAUD(row.repayment)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs font-medium">
                      ${fmtAUD(row.closing_balance)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs text-muted-foreground">
                      {fmtRate(row.interest_rate_applied)}
                    </td>
                  </tr>
                ))}
                {fac.schedule.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-4 text-center text-xs text-muted-foreground">
                      No budget schedule yet. Set forecast assumptions above and run
                      &ldquo;Save &amp; Calculate&rdquo; on the Assumptions page.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Metric Box ────────────────────────────────────────────────────── */

function MetricBox({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg bg-muted/40 p-3">
      <div className="text-xs text-muted-foreground mb-0.5">{label}</div>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
