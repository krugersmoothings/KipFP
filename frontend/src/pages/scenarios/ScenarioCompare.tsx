import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type {
  BudgetVersion,
  ScenarioRead,
  ScenarioCompareResponse,
  ScenarioMetric,
} from "@/types/api";

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
}

function fmtPct(n: number | null): string {
  if (n === null) return "-";
  return `${n.toFixed(1)}%`;
}

const METRIC_ROWS: { key: keyof ScenarioMetric; label: string; format: "aud" | "pct" }[] = [
  { key: "revenue", label: "Revenue", format: "aud" },
  { key: "gm_pct", label: "Gross Margin %", format: "pct" },
  { key: "ebitda", label: "EBITDA", format: "aud" },
  { key: "ebitda_pct", label: "EBITDA %", format: "pct" },
  { key: "npat", label: "NPAT", format: "aud" },
  { key: "operating_cf", label: "Operating Cash Flow", format: "aud" },
  { key: "closing_cash", label: "Closing Cash", format: "aud" },
  { key: "total_debt", label: "Total Debt", format: "aud" },
];

export default function ScenarioCompare() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const { data: scenarios } = useQuery<ScenarioRead[]>({
    queryKey: ["scenarios", activeVersionId],
    queryFn: async () => {
      const res = await api.get("/api/v1/scenarios/", {
        params: { version_id: activeVersionId },
      });
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  // Include the base version in the comparison options
  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const compareIds = selectedIds.length > 0
    ? selectedIds.join(",")
    : null;

  const { data: comparison, isLoading } = useQuery<ScenarioCompareResponse>({
    queryKey: ["scenario-compare", compareIds],
    queryFn: async () => {
      const res = await api.get("/api/v1/scenarios/compare", {
        params: { ids: compareIds },
      });
      return res.data;
    },
    enabled: !!compareIds,
  });

  const toggleId = (id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 5) return prev;
      return [...prev, id];
    });
  };

  const allOptions = [
    ...(activeVersionId && versions
      ? versions
          .filter((v) => v.id === activeVersionId)
          .map((v) => ({ id: v.id, name: `${v.name} (Base)` }))
      : []),
    ...(scenarios?.map((s) => ({ id: s.id, name: s.name })) ?? []),
  ];

  const baseMetric = comparison?.scenarios?.[0];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/scenarios">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Compare Scenarios</h1>
          <p className="text-muted-foreground">
            FY{fyYear} &middot; Select up to 5 scenarios
          </p>
        </div>
      </div>

      {/* Selector */}
      <Card className="p-4">
        <div className="flex flex-wrap gap-2">
          {allOptions.map((opt) => (
            <button
              key={opt.id}
              onClick={() => toggleId(opt.id)}
              className={`rounded-full px-3 py-1.5 text-sm font-medium border transition-colors ${
                selectedIds.includes(opt.id)
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-foreground border-border hover:bg-accent"
              }`}
            >
              {opt.name}
            </button>
          ))}
        </div>
        {selectedIds.length === 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            Click scenarios to add them to the comparison.
          </p>
        )}
      </Card>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {comparison && comparison.scenarios.length > 0 && (
        <>
          {/* Summary metric cards */}
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${comparison.scenarios.length}, 1fr)` }}>
            {comparison.scenarios.map((s) => (
              <Card key={s.scenario_id} className="p-4 text-center">
                <p className="text-sm font-medium truncate">{s.scenario_name}</p>
                <p className="mt-1 text-2xl font-bold tabular-nums">
                  {fmtAUD(s.revenue)}
                </p>
                <p className="text-xs text-muted-foreground">Revenue</p>
                <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-xs">
                  <span className="text-muted-foreground text-right">EBITDA</span>
                  <span className="tabular-nums">{fmtAUD(s.ebitda)}</span>
                  <span className="text-muted-foreground text-right">NPAT</span>
                  <span className="tabular-nums">{fmtAUD(s.npat)}</span>
                  <span className="text-muted-foreground text-right">Cash</span>
                  <span className="tabular-nums">{fmtAUD(s.closing_cash)}</span>
                </div>
              </Card>
            ))}
          </div>

          {/* Detail comparison table */}
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium min-w-[180px]">Metric</th>
                  {comparison.scenarios.map((s) => (
                    <th key={s.scenario_id} className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[120px]">
                      {s.scenario_name}
                    </th>
                  ))}
                  {comparison.scenarios.length > 1 && (
                    <th className="px-4 py-3 text-right font-medium whitespace-nowrap min-w-[100px]">
                      Delta
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {METRIC_ROWS.map((mr) => (
                  <tr key={mr.key} className="border-b last:border-0">
                    <td className="px-4 py-2 font-medium">{mr.label}</td>
                    {comparison.scenarios.map((s) => {
                      const val = s[mr.key] as number | null;
                      return (
                        <td key={s.scenario_id} className="px-4 py-2 text-right tabular-nums">
                          {mr.format === "pct" ? fmtPct(val) : fmtAUD(val ?? 0)}
                        </td>
                      );
                    })}
                    {comparison.scenarios.length > 1 && baseMetric && (
                      <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                        {(() => {
                          const last = comparison.scenarios[comparison.scenarios.length - 1];
                          const baseVal = (baseMetric[mr.key] as number | null) ?? 0;
                          const lastVal = (last[mr.key] as number | null) ?? 0;
                          const delta = lastVal - baseVal;
                          if (mr.format === "pct") return fmtPct(delta);
                          return fmtAUD(delta);
                        })()}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {compareIds && comparison && comparison.scenarios.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No output data found for the selected scenarios. Ensure the model has been calculated.
        </div>
      )}
    </div>
  );
}
