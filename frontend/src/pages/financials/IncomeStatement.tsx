import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Download, Building2, Calendar } from "lucide-react";
import api from "@/utils/api";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import FinancialTable from "@/components/FinancialTable";
import type { CellClickInfo } from "@/components/FinancialTable";
import DrillDownModal from "@/components/DrillDownModal";
import type { FinancialStatementResponse } from "@/types/api";

type ViewMode = "period" | "entity";

export default function IncomeStatement() {
  const { fyYear, fyMonth } = usePeriodStore();
  const [viewMode, setViewMode] = useState<ViewMode>("period");
  const [exporting, setExporting] = useState(false);
  const [drillDown, setDrillDown] = useState<CellClickInfo | null>(null);

  const { data, isLoading, error, refetch } = useQuery<FinancialStatementResponse>({
    queryKey: ["consolidated-is", fyYear, fyMonth, viewMode],
    queryFn: async () => {
      const params: Record<string, unknown> = { fy_year: fyYear, fy_month: fyMonth };
      if (viewMode === "entity") params.group_by = "entity";
      const res = await api.get("/api/v1/consolidated/is", { params });
      return res.data;
    },
  });

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const res = await api.post(
        "/api/v1/reports/export",
        { type: "actuals", fy_year: fyYear, format: "xlsx" },
        { responseType: "blob" }
      );
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `kip_actuals_FY${fyYear}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      // FIX(M22): surface export errors to the user
      alert("Export failed — please try again.");
    } finally {
      setExporting(false);
    }
  }, [fyYear]);

  const handleCellClick = useCallback((info: CellClickInfo) => {
    setDrillDown(info);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Consolidated Income Statement
          </h1>
          <p className="text-muted-foreground">
            FY{fyYear} &middot; to M{String(fyMonth).padStart(2, "0")}
            {viewMode === "period" ? " — Monthly + YTD vs Budget" : " — By Entity"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            Export Excel
          </Button>
          <div className="flex rounded-md border">
            <button
              onClick={() => setViewMode("period")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === "period"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              } rounded-l-md`}
            >
              <Calendar className="h-3.5 w-3.5" /> By Period
            </button>
            <button
              onClick={() => setViewMode("entity")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === "entity"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              } rounded-r-md`}
            >
              <Building2 className="h-3.5 w-3.5" /> By Entity
            </button>
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Failed to load income statement data.</p>
          <p className="mt-1 text-xs opacity-80">
            {(error as any)?.response?.status &&
              `${(error as any).response.status}: `}
            {(error as any)?.response?.data?.detail ?? error.message}
          </p>
          <Button variant="outline" size="sm" className="mt-2" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      )}

      {data && data.rows.length > 0 && (
        <FinancialTable
          rows={data.rows}
          periods={data.periods}
          showEntityBreakdown={false}
          highlightVariance={viewMode === "period"}
          onCellClick={handleCellClick}
        />
      )}

      {data && data.rows.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No income statement data available for this period. Run a
          consolidation first.
        </div>
      )}

      {drillDown && (
        <DrillDownModal
          info={drillDown}
          fyYear={fyYear}
          fyMonth={fyMonth}
          onClose={() => setDrillDown(null)}
        />
      )}
    </div>
  );
}
