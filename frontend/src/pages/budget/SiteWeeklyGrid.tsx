import { useEffect, useState, useMemo } from "react";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import api from "@/utils/api";
import type {
  BudgetVersion,
  SiteWeeklyBudgetRow,
  SiteAnnualSummary,
} from "@/types/api";

const AUD = (v: number | null | undefined) =>
  v != null
    ? `$${Math.round(v).toLocaleString("en-AU")}`
    : "–";

const NUM = (v: number | null | undefined) =>
  v != null ? v.toLocaleString("en-AU") : "–";

function cellHighlight(budget: number | null, prior: number | null): string {
  if (budget == null || prior == null || prior === 0) return "";
  const ratio = budget / prior;
  if (ratio > 1.2) return "bg-amber-50 text-amber-800";
  if (ratio < 0.9) return "bg-red-50 text-red-700";
  return "";
}

export default function SiteWeeklyGrid() {
  const versionId = useBudgetStore((s) => s.activeVersionId);
  const fyYear = usePeriodStore((s) => s.fyYear);
  const setActiveVersionId = useBudgetStore((s) => s.setActiveVersionId);

  const [versions, setVersions] = useState<BudgetVersion[]>([]);
  const [sites, setSites] = useState<SiteAnnualSummary[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [rows, setRows] = useState<SiteWeeklyBudgetRow[]>([]);
  const [editingCell, setEditingCell] = useState<{ weekId: string; field: string } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get<BudgetVersion[]>(`/api/v1/budgets/?fy_year=${fyYear}`).then((r) => {
      setVersions(r.data);
      if (!versionId && r.data.length > 0) {
        setActiveVersionId(r.data[0].id);
      }
    });
  }, [fyYear]);

  useEffect(() => {
    if (!versionId) return;
    api
      .get<SiteAnnualSummary[]>(`/api/v1/budgets/${versionId}/sites/annual-summary`)
      .then((r) => setSites(r.data));
  }, [versionId]);

  useEffect(() => {
    if (!versionId || !selectedSiteId) {
      setRows([]);
      return;
    }
    setLoading(true);
    api
      .get<SiteWeeklyBudgetRow[]>(
        `/api/v1/budgets/${versionId}/sites/${selectedSiteId}/weekly`,
      )
      .then((r) => setRows(r.data))
      .finally(() => setLoading(false));
  }, [versionId, selectedSiteId]);

  const annualTotal = useMemo(() => {
    const data = rows.filter((r) => !r.is_month_subtotal);
    return {
      priorPd:
        data.reduce(
          (s, r) =>
            s +
            (r.prior_year_pet_days_boarding ?? 0) +
            (r.prior_year_pet_days_daycare ?? 0),
          0,
        ),
      budgetPd:
        data.reduce(
          (s, r) =>
            s +
            (r.budget_pet_days_boarding ?? 0) +
            (r.budget_pet_days_daycare ?? 0),
          0,
        ),
      priorRev: data.reduce((s, r) => s + (r.prior_year_revenue ?? 0), 0),
      budgetRev: data.reduce((s, r) => s + (r.budget_revenue ?? 0), 0),
      budgetLabour: data.reduce((s, r) => s + (r.budget_labour ?? 0), 0),
      budgetContrib: data.reduce(
        (s, r) =>
          s +
          (r.budget_revenue ?? 0) -
          (r.budget_labour ?? 0) -
          (r.budget_cogs ?? 0) -
          (r.budget_rent ?? 0) -
          (r.budget_utilities ?? 0) -
          (r.budget_rm ?? 0) -
          (r.budget_it ?? 0) -
          (r.budget_general ?? 0) -
          (r.budget_advertising ?? 0),
        0,
      ),
    };
  }, [rows]);

  const handleCellClick = (weekId: string, field: string, currentValue: number | null) => {
    setEditingCell({ weekId, field });
    setEditValue(currentValue != null ? String(currentValue) : "");
  };

  const handleCellSave = async () => {
    if (!editingCell || !versionId || !selectedSiteId) return;
    const { weekId, field } = editingCell;
    const value = parseFloat(editValue) || 0;

    const payload: Record<string, number | boolean> = { is_overridden: true };
    if (field === "revenue") payload.override_revenue = value;
    if (field === "labour") payload.override_labour = value;

    await api.put(
      `/api/v1/budgets/${versionId}/sites/${selectedSiteId}/weekly/${weekId}/override`,
      payload,
    );
    setEditingCell(null);

    const { data } = await api.get<SiteWeeklyBudgetRow[]>(
      `/api/v1/budgets/${versionId}/sites/${selectedSiteId}/weekly`,
    );
    setRows(data);
  };

  const handleExport = async () => {
    if (!versionId || !selectedSiteId) return;
    const siteName = sites.find((s) => s.location_id === selectedSiteId)?.location_name || "site";
    const csvRows = [
      [
        "Week",
        "Start",
        "End",
        "PY Boarding",
        "PY Daycare",
        "PY Revenue",
        "Budget Boarding",
        "Budget Daycare",
        "Budget Revenue",
        "Budget Labour",
        "Contribution",
      ].join(","),
    ];
    for (const r of rows.filter((r) => !r.is_month_subtotal)) {
      const contrib =
        (r.budget_revenue ?? 0) -
        (r.budget_labour ?? 0) -
        (r.budget_cogs ?? 0) -
        (r.budget_rent ?? 0) -
        (r.budget_utilities ?? 0) -
        (r.budget_rm ?? 0) -
        (r.budget_it ?? 0) -
        (r.budget_general ?? 0) -
        (r.budget_advertising ?? 0);
      csvRows.push(
        [
          r.week_label,
          r.week_start,
          r.week_end,
          r.prior_year_pet_days_boarding,
          r.prior_year_pet_days_daycare,
          r.prior_year_revenue?.toFixed(2),
          r.budget_pet_days_boarding,
          r.budget_pet_days_daycare,
          r.budget_revenue?.toFixed(2),
          r.budget_labour?.toFixed(2),
          contrib.toFixed(2),
        ].join(","),
      );
    }
    const blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${siteName}_weekly_budget.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Weekly Budget Grid</h1>
        <div className="flex items-center gap-3">
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
          <select
            className="rounded border px-3 py-1.5 text-sm min-w-[200px]"
            value={selectedSiteId || ""}
            onChange={(e) => setSelectedSiteId(e.target.value || null)}
          >
            <option value="">Select site…</option>
            {sites.map((s) => (
              <option key={s.location_id} value={s.location_id}>
                {s.location_name}
              </option>
            ))}
          </select>
          {selectedSiteId && (
            <button
              onClick={handleExport}
              className="rounded bg-muted px-3 py-1.5 text-sm font-medium hover:bg-muted/80"
            >
              Export CSV
            </button>
          )}
        </div>
      </div>

      {!versionId || !selectedSiteId ? (
        <p className="text-muted-foreground">Select a version and site to view the weekly budget.</p>
      ) : loading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-muted-foreground">
          No weekly budget data. Run "Save & Calculate" on the Site Setup page first.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">Week</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">PY Boarding</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">Bdg Boarding</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">PY Daycare</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">Bdg Daycare</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">PY Revenue</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">Bdg Revenue</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">Labour</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-semibold">Contribution</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const isSubtotal = r.is_month_subtotal;
                const contrib =
                  (r.budget_revenue ?? 0) -
                  (r.budget_labour ?? 0) -
                  (r.budget_cogs ?? 0) -
                  (r.budget_rent ?? 0) -
                  (r.budget_utilities ?? 0) -
                  (r.budget_rm ?? 0) -
                  (r.budget_it ?? 0) -
                  (r.budget_general ?? 0) -
                  (r.budget_advertising ?? 0);

                return (
                  <tr
                    key={`${r.week_id}-${i}`}
                    className={`border-b ${
                      isSubtotal
                        ? "bg-muted/30 font-semibold"
                        : r.is_overridden
                          ? "bg-blue-50/50"
                          : ""
                    }`}
                  >
                    <td className="whitespace-nowrap px-3 py-1.5">
                      <div>{r.week_label || "–"}</div>
                      {!isSubtotal && r.week_start && (
                        <div className="text-xs text-muted-foreground">
                          {r.week_start}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {isSubtotal ? "" : NUM(r.prior_year_pet_days_boarding)}
                    </td>
                    <td
                      className={`px-3 py-1.5 text-right ${
                        isSubtotal
                          ? ""
                          : cellHighlight(
                              r.budget_pet_days_boarding,
                              r.prior_year_pet_days_boarding,
                            )
                      }`}
                    >
                      {isSubtotal ? "" : NUM(r.budget_pet_days_boarding)}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {isSubtotal ? "" : NUM(r.prior_year_pet_days_daycare)}
                    </td>
                    <td
                      className={`px-3 py-1.5 text-right ${
                        isSubtotal
                          ? ""
                          : cellHighlight(
                              r.budget_pet_days_daycare,
                              r.prior_year_pet_days_daycare,
                            )
                      }`}
                    >
                      {isSubtotal ? "" : NUM(r.budget_pet_days_daycare)}
                    </td>
                    <td className="px-3 py-1.5 text-right">{AUD(r.prior_year_revenue)}</td>
                    <td
                      className={`px-3 py-1.5 text-right cursor-pointer ${cellHighlight(r.budget_revenue, r.prior_year_revenue)}`}
                      onClick={() => {
                        if (!isSubtotal)
                          handleCellClick(r.week_id, "revenue", r.budget_revenue);
                      }}
                    >
                      {editingCell?.weekId === r.week_id &&
                      editingCell?.field === "revenue" ? (
                        <input
                          type="number"
                          className="w-24 rounded border px-1 py-0.5 text-right text-sm"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onBlur={handleCellSave}
                          onKeyDown={(e) =>
                            e.key === "Enter" && handleCellSave()
                          }
                          autoFocus
                        />
                      ) : (
                        AUD(r.budget_revenue)
                      )}
                    </td>
                    <td
                      className="px-3 py-1.5 text-right cursor-pointer"
                      onClick={() => {
                        if (!isSubtotal)
                          handleCellClick(r.week_id, "labour", r.budget_labour);
                      }}
                    >
                      {editingCell?.weekId === r.week_id &&
                      editingCell?.field === "labour" ? (
                        <input
                          type="number"
                          className="w-24 rounded border px-1 py-0.5 text-right text-sm"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onBlur={handleCellSave}
                          onKeyDown={(e) =>
                            e.key === "Enter" && handleCellSave()
                          }
                          autoFocus
                        />
                      ) : (
                        AUD(r.budget_labour)
                      )}
                    </td>
                    <td
                      className={`px-3 py-1.5 text-right font-medium ${
                        contrib < 0 ? "text-red-600" : "text-green-700"
                      }`}
                    >
                      {AUD(contrib)}
                    </td>
                  </tr>
                );
              })}

              {/* Annual total row */}
              <tr className="border-t-2 bg-muted font-bold">
                <td className="px-3 py-2">Annual Total</td>
                <td className="px-3 py-2 text-right">{NUM(annualTotal.priorPd)}</td>
                <td className="px-3 py-2 text-right">{NUM(annualTotal.budgetPd)}</td>
                <td className="px-3 py-2 text-right" />
                <td className="px-3 py-2 text-right" />
                <td className="px-3 py-2 text-right">{AUD(annualTotal.priorRev)}</td>
                <td className="px-3 py-2 text-right">{AUD(annualTotal.budgetRev)}</td>
                <td className="px-3 py-2 text-right">{AUD(annualTotal.budgetLabour)}</td>
                <td
                  className={`px-3 py-2 text-right ${
                    annualTotal.budgetContrib < 0 ? "text-red-600" : "text-green-700"
                  }`}
                >
                  {AUD(annualTotal.budgetContrib)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
