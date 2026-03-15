import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import api from "@/utils/api";
import { usePeriodStore, periodLabel } from "@/stores/period";
import { useBudgetStore } from "@/stores/budget";
import FinancialTable from "@/components/FinancialTable";
import type { FinancialStatementResponse, BudgetVersion } from "@/types/api";

export default function CashFlow() {
  const { fyYear, dataPreparedToFyYear, dataPreparedToFyMonth } = usePeriodStore();
  const { activeVersionId, setActiveVersionId } = useBudgetStore();

  const lastActualMonth = dataPreparedToFyMonth;
  const closedLabel = periodLabel(dataPreparedToFyYear, dataPreparedToFyMonth);

  const versions = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/budgets/", {
        params: { fy_year: fyYear },
      });
      return data;
    },
  });

  const versionId = activeVersionId || versions.data?.[0]?.id;

  const cf = useQuery<FinancialStatementResponse>({
    queryKey: ["blended-cf", fyYear, lastActualMonth, versionId],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/consolidated/cf/blended", {
        params: {
          fy_year: fyYear,
          last_actual_month: lastActualMonth,
          version_id: versionId,
        },
      });
      return data;
    },
    enabled: !!versionId,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Cash Flow — Actuals + Forecast
          </h1>
          <p className="text-muted-foreground">
            FY{fyYear} &middot; Actuals to {closedLabel}, then forecast
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm">
            <label className="text-muted-foreground whitespace-nowrap">Forecast</label>
            <select
              value={versionId ?? ""}
              onChange={(e) => setActiveVersionId(e.target.value || null)}
              className="rounded-md border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {versions.data?.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
              {(!versions.data || versions.data.length === 0) && (
                <option value="">No versions</option>
              )}
            </select>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500" />
          Actuals (to {closedLabel})
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-blue-500" />
          Forecast
        </span>
      </div>

      {cf.isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {cf.isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load cash flow data. Make sure a budget version exists for FY{fyYear}.
        </div>
      )}

      {!versionId && !cf.isLoading && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No budget/forecast version found for FY{fyYear}. Create one in Budget &rarr; Assumptions first.
        </div>
      )}

      {cf.data && cf.data.rows.length > 0 && (
        <FinancialTable
          rows={cf.data.rows}
          periods={cf.data.periods}
          highlightVariance={false}
          lastActualMonth={lastActualMonth}
        />
      )}
    </div>
  );
}
