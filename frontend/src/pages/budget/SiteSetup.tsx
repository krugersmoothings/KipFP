import { useEffect, useState, useMemo, useCallback } from "react";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import api from "@/utils/api";
import type {
  BudgetVersion,
  LocationRead,
  SiteBudgetAssumption,
  SiteBudgetAssumptionUpdate,
  SiteAnnualSummary,
} from "@/types/api";

const AUD = (v: number | null | undefined) =>
  v != null ? `$${v.toLocaleString("en-AU", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` : "–";

const PCT = (v: number | null | undefined) =>
  v != null ? `${(v * 100).toFixed(1)}%` : "–";

const NUM = (v: number | null | undefined) =>
  v != null ? v.toLocaleString("en-AU") : "–";

type SiteGroup = { state: string; sites: SiteAnnualSummary[] };

function groupByState(sites: SiteAnnualSummary[]): SiteGroup[] {
  const map: Record<string, SiteAnnualSummary[]> = {};
  for (const s of sites) {
    const st = s.state || "Other";
    if (!map[st]) map[st] = [];
    map[st].push(s);
  }
  return Object.entries(map)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([state, sites]) => ({ state, sites }));
}

function statusBadge(status: string) {
  if (status === "set" || status === "locked")
    return <span className="inline-block h-2 w-2 rounded-full bg-green-500" title="Assumptions set" />;
  if (status === "default")
    return <span className="inline-block h-2 w-2 rounded-full bg-amber-400" title="Using defaults" />;
  return <span className="inline-block h-2 w-2 rounded-full bg-gray-300" title="No prior year data" />;
}

interface PctFieldProps {
  label: string;
  value: number | null | undefined;
  onChange: (v: number) => void;
  readOnly?: boolean;
}

function PctField({ label, value, onChange, readOnly }: PctFieldProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <label className="text-sm text-muted-foreground whitespace-nowrap">{label}</label>
      {readOnly ? (
        <span className="text-sm font-medium">{PCT(value)}</span>
      ) : (
        <input
          type="number"
          step="0.1"
          className="w-20 rounded border px-2 py-1 text-right text-sm"
          value={value != null ? (value * 100).toFixed(1) : ""}
          onChange={(e) => {
            const parsed = parseFloat(e.target.value);
            // FIX(H21): guard against NaN propagation
            onChange(isNaN(parsed) ? 0 : parsed / 100);
          }}
        />
      )}
    </div>
  );
}

interface MoneyFieldProps {
  label: string;
  value: number | null | undefined;
  onChange: (v: number) => void;
  readOnly?: boolean;
}

function MoneyField({ label, value, onChange, readOnly }: MoneyFieldProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <label className="text-sm text-muted-foreground whitespace-nowrap">{label}</label>
      {readOnly ? (
        <span className="text-sm font-medium">{AUD(value)}</span>
      ) : (
        <input
          type="number"
          step="100"
          className="w-28 rounded border px-2 py-1 text-right text-sm"
          value={value ?? ""}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        />
      )}
    </div>
  );
}

interface NumFieldProps {
  label: string;
  value: number | null | undefined;
  onChange: (v: number) => void;
}

function NumField({ label, value, onChange }: NumFieldProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <label className="text-sm text-muted-foreground whitespace-nowrap">{label}</label>
      <input
        type="number"
        step="0.5"
        className="w-20 rounded border px-2 py-1 text-right text-sm"
        value={value ?? ""}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      />
    </div>
  );
}

export default function SiteSetup() {
  const versionId = useBudgetStore((s) => s.activeVersionId);
  const fyYear = usePeriodStore((s) => s.fyYear);

  const [versions, setVersions] = useState<BudgetVersion[]>([]);
  const [sites, setSites] = useState<SiteAnnualSummary[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [assumptions, setAssumptions] = useState<SiteBudgetAssumption | null>(null);
  const [localEdits, setLocalEdits] = useState<SiteBudgetAssumptionUpdate>({});
  const [saving, setSaving] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [bulkGrowth, setBulkGrowth] = useState({ price: 3.0, petDay: 2.0, wage: 5.0 });

  const setActiveVersionId = useBudgetStore((s) => s.setActiveVersionId);

  // FIX(M38): add error handling to all useEffect API calls
  useEffect(() => {
    api.get<BudgetVersion[]>(`/api/v1/budgets/?fy_year=${fyYear}`)
      .then((r) => {
        setVersions(r.data);
        if (!versionId && r.data.length > 0) {
          setActiveVersionId(r.data[0].id);
        }
      })
      .catch(() => setVersions([]));
  }, [fyYear]);

  useEffect(() => {
    if (!versionId) return;
    api
      .get<SiteAnnualSummary[]>(`/api/v1/budgets/${versionId}/sites/annual-summary`)
      .then((r) => setSites(r.data))
      .catch(() => setSites([]));
  }, [versionId]);

  useEffect(() => {
    if (!versionId || !selectedSiteId) {
      setAssumptions(null);
      return;
    }
    api
      .get<SiteBudgetAssumption>(`/api/v1/budgets/${versionId}/sites/${selectedSiteId}/assumptions`)
      .then((r) => {
        setAssumptions(r.data);
        setLocalEdits({});
      })
      .catch(() => setAssumptions(null));
  }, [versionId, selectedSiteId]);

  const groups = useMemo(() => groupByState(sites), [sites]);

  const merged = useMemo(() => {
    if (!assumptions) return null;
    return { ...assumptions, ...localEdits };
  }, [assumptions, localEdits]);

  const impliedRevenue = useMemo(() => {
    if (!merged || !merged.prior_year_avg_price || !merged.prior_year_total_pet_days) return 0;
    const price = merged.prior_year_avg_price * (1 + (merged.price_growth_pct ?? 0.03));
    const pd = merged.prior_year_total_pet_days * (1 + (merged.pet_day_growth_pct ?? 0.02));
    return price * pd;
  }, [merged]);

  const impliedLabour = useMemo(() => {
    if (!merged || !merged.prior_year_total_pet_days || !merged.prior_year_avg_wage) return 0;
    const pd = merged.prior_year_total_pet_days * (1 + (merged.pet_day_growth_pct ?? 0.02));
    const mpp = merged.mpp_mins ?? 15;
    // FIX(M44): use operating_days from assumptions if available, fallback to 365
    const operatingDays = (merged as Record<string, unknown>).operating_days_per_year as number ?? 365;
    const minHours = (merged.min_daily_hours ?? 8) * operatingDays;
    const hoursFromPd = (pd * mpp) / 60;
    const hours = Math.max(hoursFromPd, minHours);
    const wage = merged.prior_year_avg_wage * (1 + (merged.wage_increase_pct ?? 0.05));
    return hours * wage;
  }, [merged]);

  const updateField = useCallback(
    (field: keyof SiteBudgetAssumptionUpdate, value: number) => {
      setLocalEdits((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  // FIX(M39): add catch blocks to surface errors to the user
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!versionId || !selectedSiteId) return;
    setSaving(true);
    setError(null);
    try {
      const { data } = await api.put<SiteBudgetAssumption>(
        `/api/v1/budgets/${versionId}/sites/${selectedSiteId}/assumptions`,
        localEdits,
      );
      setAssumptions(data);
      setLocalEdits({});
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Save failed";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndCalculate = async () => {
    if (!versionId || !selectedSiteId) return;
    setSaving(true);
    setCalculating(true);
    setError(null);
    try {
      await api.put(`/api/v1/budgets/${versionId}/sites/${selectedSiteId}/assumptions`, localEdits);
      await api.post(`/api/v1/budgets/${versionId}/sites/${selectedSiteId}/calculate`);
      const { data } = await api.get<SiteBudgetAssumption>(
        `/api/v1/budgets/${versionId}/sites/${selectedSiteId}/assumptions`,
      );
      setAssumptions(data);
      setLocalEdits({});
      const { data: refreshed } = await api.get<SiteAnnualSummary[]>(
        `/api/v1/budgets/${versionId}/sites/annual-summary`,
      );
      setSites(refreshed);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Save & Calculate failed";
      setError(msg);
    } finally {
      setSaving(false);
      setCalculating(false);
    }
  };

  const handleBulkApply = async () => {
    if (!versionId) return;
    await api.put(`/api/v1/budgets/${versionId}/sites/bulk-assumptions`, {
      price_growth_pct: bulkGrowth.price / 100,
      pet_day_growth_pct: bulkGrowth.petDay / 100,
      wage_increase_pct: bulkGrowth.wage / 100,
    });
    if (selectedSiteId) {
      const { data } = await api.get<SiteBudgetAssumption>(
        `/api/v1/budgets/${versionId}/sites/${selectedSiteId}/assumptions`,
      );
      setAssumptions(data);
      setLocalEdits({});
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Site Assumption Editor</h1>
        <select
          className="rounded border px-3 py-1.5 text-sm"
          value={versionId || ""}
          onChange={(e) => setActiveVersionId(e.target.value || null)}
        >
          <option value="">Select version…</option>
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} (FY{v.fy_year})
            </option>
          ))}
        </select>
      </div>

      {!versionId ? (
        <p className="text-muted-foreground">Select a budget version to begin.</p>
      ) : (
        <div className="grid grid-cols-12 gap-6">
          {/* Left panel — site list */}
          <div className="col-span-4 space-y-1 rounded-lg border bg-card p-4 max-h-[calc(100vh-12rem)] overflow-y-auto">
            {groups.map((g) => (
              <div key={g.state} className="mb-3">
                <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground tracking-wider">
                  {g.state}
                </div>
                {g.sites.map((s) => (
                  <button
                    key={s.location_id}
                    onClick={() => setSelectedSiteId(s.location_id)}
                    className={`flex w-full items-center justify-between rounded px-3 py-1.5 text-sm transition-colors ${
                      selectedSiteId === s.location_id
                        ? "bg-primary text-primary-foreground"
                        : "hover:bg-accent"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      {statusBadge(s.assumptions_status)}
                      {s.location_name}
                    </span>
                    <span className="text-xs opacity-70">
                      {s.total_budget_revenue > 0 ? AUD(s.total_budget_revenue) : "–"}
                    </span>
                  </button>
                ))}
              </div>
            ))}

            {/* Bulk apply section */}
            <div className="mt-6 rounded-lg border p-3 space-y-2">
              <div className="text-xs font-semibold uppercase text-muted-foreground">Apply to All Sites</div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs">Price growth %</span>
                  <input
                    type="number"
                    step="0.1"
                    className="w-16 rounded border px-1 py-0.5 text-right text-xs"
                    value={bulkGrowth.price}
                    onChange={(e) => setBulkGrowth((p) => ({ ...p, price: parseFloat(e.target.value) || 0 }))}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">Pet day growth %</span>
                  <input
                    type="number"
                    step="0.1"
                    className="w-16 rounded border px-1 py-0.5 text-right text-xs"
                    value={bulkGrowth.petDay}
                    onChange={(e) => setBulkGrowth((p) => ({ ...p, petDay: parseFloat(e.target.value) || 0 }))}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">Wage increase %</span>
                  <input
                    type="number"
                    step="0.1"
                    className="w-16 rounded border px-1 py-0.5 text-right text-xs"
                    value={bulkGrowth.wage}
                    onChange={(e) => setBulkGrowth((p) => ({ ...p, wage: parseFloat(e.target.value) || 0 }))}
                  />
                </div>
              </div>
              <button
                onClick={handleBulkApply}
                className="w-full rounded bg-muted px-3 py-1.5 text-xs font-medium hover:bg-muted/80"
              >
                Apply to All
              </button>
            </div>
          </div>

          {/* Right panel — assumption editor */}
          <div className="col-span-8">
            {!selectedSiteId ? (
              <div className="flex h-64 items-center justify-center rounded-lg border bg-card">
                <p className="text-muted-foreground">Select a site to edit assumptions</p>
              </div>
            ) : !merged ? (
              <div className="flex h-64 items-center justify-center rounded-lg border bg-card">
                <p className="text-muted-foreground">Loading…</p>
              </div>
            ) : (
              <div className="space-y-4 rounded-lg border bg-card p-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">
                    {sites.find((s) => s.location_id === selectedSiteId)?.location_name}
                  </h2>
                  <span className="text-xs text-muted-foreground">
                    Based on FY{(merged.fy_year ?? fyYear) - 1} actuals
                  </span>
                </div>

                {/* Revenue section */}
                <div className="space-y-2 rounded border p-4">
                  <h3 className="text-sm font-semibold text-primary">Revenue</h3>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-2">
                    <MoneyField
                      label="Prior year avg price"
                      value={merged.prior_year_avg_price}
                      onChange={() => {}}
                      readOnly
                    />
                    <PctField
                      label="Price growth %"
                      value={merged.price_growth_pct}
                      onChange={(v) => updateField("price_growth_pct", v)}
                    />
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm text-muted-foreground">Prior year pet days</span>
                      <span className="text-sm font-medium">{NUM(merged.prior_year_total_pet_days)}</span>
                    </div>
                    <PctField
                      label="Pet day growth %"
                      value={merged.pet_day_growth_pct}
                      onChange={(v) => updateField("pet_day_growth_pct", v)}
                    />
                  </div>
                  <div className="mt-2 rounded bg-muted/50 px-3 py-2 text-sm">
                    Implied FY{merged.fy_year} revenue: <strong>{AUD(impliedRevenue)}</strong>
                  </div>
                </div>

                {/* Labour section */}
                <div className="space-y-2 rounded border p-4">
                  <h3 className="text-sm font-semibold text-primary">Labour</h3>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-2">
                    <NumField
                      label="Mins per pet (MPP)"
                      value={merged.mpp_mins}
                      onChange={(v) => updateField("mpp_mins", v)}
                    />
                    <NumField
                      label="Min daily hours"
                      value={merged.min_daily_hours}
                      onChange={(v) => updateField("min_daily_hours", v)}
                    />
                    <MoneyField
                      label="Prior year avg wage"
                      value={merged.prior_year_avg_wage}
                      onChange={() => {}}
                      readOnly
                    />
                    <PctField
                      label="Wage increase %"
                      value={merged.wage_increase_pct}
                      onChange={(v) => updateField("wage_increase_pct", v)}
                    />
                  </div>
                  <div className="mt-2 rounded bg-muted/50 px-3 py-2 text-sm">
                    Implied annual labour: <strong>{AUD(impliedLabour)}</strong>
                  </div>
                </div>

                {/* Fixed costs section */}
                <div className="space-y-2 rounded border p-4">
                  <h3 className="text-sm font-semibold text-primary">Fixed Costs</h3>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-2">
                    <MoneyField label="Rent /month" value={merged.rent_monthly} onChange={(v) => updateField("rent_monthly", v)} />
                    <PctField label="Rent growth %" value={merged.rent_growth_pct} onChange={(v) => updateField("rent_growth_pct", v)} />
                    <MoneyField label="Utilities /month" value={merged.utilities_monthly} onChange={(v) => updateField("utilities_monthly", v)} />
                    <PctField label="Utilities growth %" value={merged.utilities_growth_pct} onChange={(v) => updateField("utilities_growth_pct", v)} />
                    <MoneyField label="R&M /month" value={merged.rm_monthly} onChange={(v) => updateField("rm_monthly", v)} />
                    <PctField label="R&M growth %" value={merged.rm_growth_pct} onChange={(v) => updateField("rm_growth_pct", v)} />
                    <MoneyField label="IT /month" value={merged.it_monthly} onChange={(v) => updateField("it_monthly", v)} />
                    <PctField label="IT growth %" value={merged.it_growth_pct} onChange={(v) => updateField("it_growth_pct", v)} />
                    <MoneyField label="General /month" value={merged.general_monthly} onChange={(v) => updateField("general_monthly", v)} />
                    <PctField label="General growth %" value={merged.general_growth_pct} onChange={(v) => updateField("general_growth_pct", v)} />
                    <PctField label="COGS %" value={merged.cogs_pct} onChange={(v) => updateField("cogs_pct", v)} />
                    <PctField label="Advertising % of rev" value={merged.advertising_pct_revenue} onChange={(v) => updateField("advertising_pct_revenue", v)} />
                  </div>
                </div>

                {error && (
                  <p className="text-sm text-red-600">{error}</p>
                )}

                {/* Actions */}
                <div className="flex gap-3">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="rounded bg-muted px-4 py-2 text-sm font-medium hover:bg-muted/80 disabled:opacity-50"
                  >
                    {saving ? "Saving…" : "Save"}
                  </button>
                  <button
                    onClick={handleSaveAndCalculate}
                    disabled={saving || calculating}
                    className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    {calculating ? "Calculating…" : "Save & Calculate"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
