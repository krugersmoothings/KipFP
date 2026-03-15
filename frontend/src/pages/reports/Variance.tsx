import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Download, MessageSquare } from "lucide-react";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import type {
  BudgetVersion,
  VarianceReportResponse,
  VarianceRow,
} from "@/types/api";

type ViewMode = "monthly" | "ytd" | "full_year";

const VIEW_TABS: { key: ViewMode; label: string }[] = [
  { key: "monthly", label: "Monthly" },
  { key: "ytd", label: "YTD" },
  { key: "full_year", label: "Full Year" },
];

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
}

function fmtPct(n: number | null): string {
  if (n === null) return "-";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function varianceBg(row: VarianceRow): string {
  if (row.is_section_header || row.is_favourable === null) return "";
  const mag = Math.abs(row.variance_pct ?? 0);
  // FIX(M32): zero-variance rows should not be highlighted
  if (mag < 0.05) return "";
  if (row.is_favourable) {
    if (mag >= 10) return "bg-green-200 dark:bg-green-900/50";
    if (mag >= 5) return "bg-green-100 dark:bg-green-900/30";
    return "bg-green-50 dark:bg-green-900/15";
  }
  if (mag >= 10) return "bg-red-200 dark:bg-red-900/50";
  if (mag >= 5) return "bg-red-100 dark:bg-red-900/30";
  return "bg-red-50 dark:bg-red-900/15";
}

export default function VariancePage() {
  const { fyYear, fyMonth } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role === "admin" || user?.role === "finance";
  const queryClient = useQueryClient();

  const [viewMode, setViewMode] = useState<ViewMode>("monthly");
  const [editingComment, setEditingComment] = useState<string | null>(null);
  const [commentText, setCommentText] = useState("");
  const [exporting, setExporting] = useState(false);

  const fyMonthParam = viewMode === "monthly" ? fyMonth : viewMode === "ytd" ? 0 : -1;

  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const { data, isLoading, error, refetch } = useQuery<VarianceReportResponse>({
    queryKey: ["variance", activeVersionId, fyYear, fyMonthParam],
    queryFn: async () => {
      const res = await api.get("/api/v1/reports/variance", {
        params: {
          fy_year: fyYear,
          fy_month: fyMonthParam,
          version_id: activeVersionId,
        },
      });
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  const commentMutation = useMutation({
    mutationFn: async (payload: { account_id: string; comment: string }) => {
      await api.put("/api/v1/reports/commentary", {
        version_id: activeVersionId,
        account_id: payload.account_id,
        period_id: null,
        comment: payload.comment,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["variance"] });
      setEditingComment(null);
    },
  });

  const handleExport = useCallback(async () => {
    if (!activeVersionId) return;
    setExporting(true);
    try {
      const res = await api.post(
        "/api/v1/reports/export",
        { type: "variance", version_id: activeVersionId, fy_year: fyYear, format: "xlsx" },
        { responseType: "blob" }
      );
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `kip_variance_FY${fyYear}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [activeVersionId, fyYear]);

  const activeVersion = versions?.find((v) => v.id === activeVersionId);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Variance Report</h1>
          <p className="text-muted-foreground">
            FY{fyYear}
            {activeVersion && <> &middot; {activeVersion.name}</>}
            {data && <> &middot; {data.period_label}</>}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleExport}
          disabled={!activeVersionId || exporting}
        >
          {exporting ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          Export Excel
        </Button>
      </div>

      {!activeVersionId && (
        <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
          Select a budget version on the Assumptions page first.
        </div>
      )}

      {activeVersionId && (
        <>
          {/* View mode tabs */}
          <div className="border-b">
            <div className="flex gap-0 -mb-px">
              {VIEW_TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setViewMode(tab.key)}
                  className={`whitespace-nowrap border-b-2 px-5 py-2.5 text-sm font-medium transition-colors ${
                    viewMode === tab.key
                      ? "border-primary text-primary"
                      : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/50"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {isLoading && (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
              <p className="font-medium">Failed to load variance data.</p>
              <Button variant="outline" size="sm" className="mt-2" onClick={() => refetch()}>
                Retry
              </Button>
            </div>
          )}

          {data && data.rows.length > 0 && (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium sticky left-0 bg-muted/50 z-10 min-w-[220px]">
                      Account
                    </th>
                    <th className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[100px]">
                      Actual
                    </th>
                    <th className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[100px]">
                      Budget
                    </th>
                    <th className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[100px]">
                      Var $
                    </th>
                    <th className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[80px]">
                      Var %
                    </th>
                    <th className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[100px]">
                      PY Actual
                    </th>
                    <th className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[80px]">
                      vs PCP %
                    </th>
                    <th className="px-4 py-3 text-left font-medium whitespace-nowrap min-w-[180px]">
                      <span className="inline-flex items-center gap-1">
                        <MessageSquare className="h-3.5 w-3.5" />
                        Commentary
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, idx) => {
                    if (row.is_section_header) {
                      return (
                        <tr key={`sh-${idx}`} className="border-b">
                          <td
                            colSpan={8}
                            className="px-4 py-2 pt-4 font-semibold text-primary tracking-wide text-xs uppercase sticky left-0 bg-background z-10"
                          >
                            {row.label}
                          </td>
                        </tr>
                      );
                    }

                    const varBg = varianceBg(row);
                    const subtotalCls = row.is_subtotal
                      ? "bg-muted/30 font-semibold border-t"
                      : "";
                    const indent = row.indent_level > 0 ? "pl-6" : "";
                    // FIX(M31): key editing on account_id (not code) since save requires it
                    const isEditingThis = editingComment === row.account_id;

                    return (
                      <tr key={row.account_code || `r-${idx}`} className={`border-b last:border-0 ${subtotalCls}`}>
                        <td className={`px-4 py-2 sticky left-0 bg-background z-10 ${indent} whitespace-nowrap`}>
                          {!row.is_subtotal && (
                            <span className="mr-2 text-muted-foreground text-xs">{row.account_code}</span>
                          )}
                          {row.label}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums">{fmtAUD(row.actual)}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{fmtAUD(row.budget)}</td>
                        <td className={`px-4 py-2 text-right tabular-nums ${varBg}`}>{fmtAUD(row.variance_abs)}</td>
                        <td className={`px-4 py-2 text-right tabular-nums ${varBg}`}>{fmtPct(row.variance_pct)}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                          {fmtAUD(row.prior_year_actual)}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                          {fmtPct(row.vs_pcp_pct)}
                        </td>
                        <td className="px-4 py-2">
                          {isEditingThis ? (
                            <div className="flex gap-1">
                              <input
                                type="text"
                                className="flex-1 rounded border px-2 py-1 text-xs"
                                value={commentText}
                                onChange={(e) => setCommentText(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" && row.account_id) {
                                    commentMutation.mutate({
                                      account_id: row.account_id,
                                      comment: commentText,
                                    });
                                  }
                                  if (e.key === "Escape") setEditingComment(null);
                                }}
                                autoFocus
                              />
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-xs"
                                onClick={() => {
                                  if (row.account_id) {
                                    commentMutation.mutate({
                                      account_id: row.account_id,
                                      comment: commentText,
                                    });
                                  }
                                }}
                              >
                                Save
                              </Button>
                            </div>
                          ) : (
                            <span
                              className={`text-xs cursor-pointer hover:underline ${
                                row.commentary ? "text-foreground" : "text-muted-foreground/50"
                              }`}
                              onClick={() => {
                                if (canEdit && !row.is_section_header && row.account_id) {
                                  setEditingComment(row.account_id);
                                  setCommentText(row.commentary || "");
                                }
                              }}
                            >
                              {row.commentary || (canEdit ? "Add note..." : "")}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {data && data.rows.length === 0 && (
            <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
              No variance data available. Ensure actuals are consolidated and the
              budget model has been calculated.
            </div>
          )}
        </>
      )}
    </div>
  );
}
