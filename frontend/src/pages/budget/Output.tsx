import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, ToggleLeft, ToggleRight } from "lucide-react";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import FinancialTable from "@/components/FinancialTable";
import type { ModelOutputResponse, BudgetVersion } from "@/types/api";

const STATEMENT_TABS = [
  { key: "is", label: "Income Statement" },
  { key: "bs", label: "Balance Sheet" },
  { key: "cf", label: "Cash Flow" },
] as const;

type StatementKey = (typeof STATEMENT_TABS)[number]["key"];

export default function BudgetOutput() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const [activeTab, setActiveTab] = useState<StatementKey>("is");
  const [showBreakdown, setShowBreakdown] = useState(false);

  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const { data, isLoading, error, refetch } = useQuery<ModelOutputResponse>({
    queryKey: ["budget-output", activeVersionId, activeTab],
    queryFn: async () => {
      const res = await api.get(
        `/api/v1/budgets/${activeVersionId}/output/${activeTab}`
      );
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  const activeVersion = versions?.find((v) => v.id === activeVersionId);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Budget Output</h1>
          <p className="text-muted-foreground">
            FY{fyYear}
            {activeVersion && <> &middot; {activeVersion.name}</>}
            {" "}&middot; 3-Statement Model
          </p>
        </div>
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

      {!activeVersionId && (
        <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
          Select a budget version on the Assumptions page first.
        </div>
      )}

      {activeVersionId && (
        <>
          {/* Tabs */}
          <div className="border-b">
            <div className="flex gap-0 -mb-px">
              {STATEMENT_TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`whitespace-nowrap border-b-2 px-5 py-2.5 text-sm font-medium transition-colors ${
                    activeTab === tab.key
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
              <p className="font-medium">Failed to load output data.</p>
              <p className="mt-1 text-xs opacity-80">
                {(error as any)?.response?.status &&
                  `${(error as any).response.status}: `}
                {(error as any)?.response?.data?.detail ?? (error as Error).message}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => refetch()}
              >
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
              No output data available. Run a calculation from the Assumptions
              page first.
            </div>
          )}
        </>
      )}
    </div>
  );
}
