import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, ToggleLeft, ToggleRight, Download } from "lucide-react";
import api from "@/utils/api";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import FinancialTable from "@/components/FinancialTable";
import type { FinancialStatementResponse } from "@/types/api";

export default function IncomeStatement() {
  const { fyYear, fyMonth } = usePeriodStore();
  const [showBreakdown, setShowBreakdown] = useState(false);
  const [exporting, setExporting] = useState(false);

  const { data, isLoading, error, refetch } = useQuery<FinancialStatementResponse>({
    queryKey: ["consolidated-is", fyYear, fyMonth],
    queryFn: async () => {
      const res = await api.get("/api/v1/consolidated/is", {
        params: { fy_year: fyYear, fy_month: fyMonth },
      });
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
    } finally {
      setExporting(false);
    }
  }, [fyYear]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Consolidated Income Statement
          </h1>
          <p className="text-muted-foreground">
            FY{fyYear} &middot; M{String(fyMonth).padStart(2, "0")} + YTD
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
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowBreakdown((b) => !b)}
          >
            {showBreakdown ? (
              <ToggleRight className="mr-2 h-4 w-4 text-primary" />
            ) : (
              <ToggleLeft className="mr-2 h-4 w-4" />
            )}
            Entity Breakdown
          </Button>
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
          showEntityBreakdown={showBreakdown}
          highlightVariance
        />
      )}

      {data && data.rows.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No income statement data available for this period. Run a
          consolidation first.
        </div>
      )}
    </div>
  );
}
