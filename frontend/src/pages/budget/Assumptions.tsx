import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Save, Check } from "lucide-react";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  BudgetVersion,
  BudgetVersionCreate,
  ModelAssumptionRead,
  AssumptionPayload,
  AssumptionKey,
  EntityRead,
  LocationRead,
  CalculationTriggerResponse,
  CalculationStatusResponse,
} from "@/types/api";

const ASSUMPTION_TABS: { key: AssumptionKey; label: string }[] = [
  { key: "revenue_growth", label: "Revenue" },
  { key: "cogs_pct", label: "COGS" },
  { key: "employment_wages", label: "Employment" },
  { key: "other_opex", label: "Other Opex" },
  { key: "capex", label: "Capex" },
  { key: "tax_rate", label: "Tax" },
];

const MONTHS = [
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
];

const TAB_DESCRIPTIONS: Record<AssumptionKey, string> = {
  revenue_growth: "Revenue growth rate (%) per location per period",
  cogs_pct: "COGS as a percentage of revenue per location",
  employment_wages: "Total wages amount ($) per location per month",
  other_opex: "Operating expenses by location",
  capex: "Monthly capital expenditure amounts ($) per location",
  tax_rate: "Effective tax rate (%) per subsidiary",
};

export default function Assumptions() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId, setActiveVersionId } = useBudgetStore();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<AssumptionKey>("revenue_growth");
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [localValues, setLocalValues] = useState<Record<string, Record<string, string>>>({});
  const [calculating, setCalculating] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  const { data: versions, isLoading: versionsLoading } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const { data: entities } = useQuery<EntityRead[]>({
    queryKey: ["entities"],
    queryFn: async () => {
      const res = await api.get("/api/v1/entities/");
      return res.data;
    },
  });

  const { data: locations } = useQuery<LocationRead[]>({
    queryKey: ["locations"],
    queryFn: async () => {
      const res = await api.get("/api/v1/entities/locations");
      return res.data;
    },
  });

  const { data: assumptions, isLoading: assumptionsLoading } = useQuery<ModelAssumptionRead[]>({
    queryKey: ["budget-assumptions", activeVersionId],
    queryFn: async () => {
      const res = await api.get(`/api/v1/budgets/${activeVersionId}/assumptions`);
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  useEffect(() => {
    if (!assumptions) return;
    const vals: Record<string, Record<string, string>> = {};
    for (const a of assumptions) {
      let rowKey: string;
      if (a.assumption_key === "tax_rate") {
        rowKey = `${a.assumption_key}::entity::${a.entity_id ?? "all"}`;
      } else {
        rowKey = `${a.assumption_key}::location::${a.location_id ?? "unknown"}`;
      }
      const monthVals: Record<string, string> = {};
      const av = a.assumption_value as Record<string, unknown>;
      for (const [k, v] of Object.entries(av)) {
        monthVals[k] = String(v ?? "");
      }
      vals[rowKey] = monthVals;
    }
    setLocalValues(vals);
  }, [assumptions]);

  const createMutation = useMutation({
    mutationFn: async (payload: BudgetVersionCreate) => {
      const res = await api.post("/api/v1/budgets/", payload);
      return res.data as BudgetVersion;
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["budget-versions"] });
      setActiveVersionId(created.id);
      setShowNewForm(false);
      setNewName("");
    },
  });

  const saveMutation = useMutation({
    mutationFn: async (payloads: AssumptionPayload[]) => {
      const res = await api.put(`/api/v1/budgets/${activeVersionId}/assumptions`, payloads);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["budget-assumptions", activeVersionId] });
    },
  });

  const buildPayloads = useCallback((): AssumptionPayload[] => {
    const payloads: AssumptionPayload[] = [];
    for (const [rowKey, monthVals] of Object.entries(localValues)) {
      const parts = rowKey.split("::");
      const key = parts[0];
      const dimension = parts[1];
      const dimId = parts[2];
      const assumptionValue: Record<string, number> = {};
      for (const [mKey, mVal] of Object.entries(monthVals)) {
        const num = parseFloat(mVal);
        if (!isNaN(num)) assumptionValue[mKey] = num;
      }
      if (dimension === "entity") {
        payloads.push({
          entity_id: dimId === "all" ? null : dimId,
          location_id: null,
          assumption_key: key as AssumptionKey,
          assumption_value: assumptionValue,
        });
      } else {
        payloads.push({
          entity_id: null,
          location_id: dimId === "unknown" ? null : dimId,
          assumption_key: key as AssumptionKey,
          assumption_value: assumptionValue,
        });
      }
    }
    return payloads;
  }, [localValues]);

  const handleSave = useCallback(() => {
    saveMutation.mutate(buildPayloads());
  }, [buildPayloads, saveMutation]);

  const handleSaveAndCalculate = useCallback(async () => {
    if (!activeVersionId) return;

    setCalculating(true);
    try {
      await saveMutation.mutateAsync(buildPayloads());
      const res = await api.post<CalculationTriggerResponse>(
        `/api/v1/budgets/${activeVersionId}/calculate`
      );
      const taskId = res.data.task_id;

      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await api.get<CalculationStatusResponse>(
            `/api/v1/budgets/${activeVersionId}/status`,
            { params: { task_id: taskId } }
          );
          const s = statusRes.data.status;
          if (s === "success" || s === "failure" || s === "revoked") {
            clearInterval(pollRef.current);
            setCalculating(false);
            if (s === "success") {
              queryClient.invalidateQueries({ queryKey: ["budget-output"] });
            }
          }
        } catch {
          clearInterval(pollRef.current);
          setCalculating(false);
        }
      }, 2000);
    } catch {
      setCalculating(false);
    }
  // FIX(L22): correct deps — uses saveMutation and buildPayloads, not handleSave
  }, [saveMutation, buildPayloads, activeVersionId, queryClient]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const updateCell = useCallback(
    (rowKey: string, monthKey: string, value: string) => {
      setLocalValues((prev) => ({
        ...prev,
        [rowKey]: { ...(prev[rowKey] ?? {}), [monthKey]: value },
      }));
    },
    []
  );

  const activeEntities = (entities ?? []).filter((e) => e.is_active);
  const activeLocations = (locations ?? []).filter((l) => l.is_active);
  const activeVersion = versions?.find((v) => v.id === activeVersionId);

  const filteredAssumptionRows = (() => {
    const rows: { rowKey: string; label: string }[] = [];
    if (activeTab === "tax_rate") {
      for (const entity of activeEntities) {
        rows.push({
          rowKey: `${activeTab}::entity::${entity.id}`,
          label: entity.name ?? entity.code,
        });
      }
    } else {
      for (const loc of activeLocations) {
        rows.push({
          rowKey: `${activeTab}::location::${loc.id}`,
          label: loc.name ?? loc.code ?? loc.id,
        });
      }
    }
    return rows;
  })();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Budget Assumptions</h1>
        <p className="text-muted-foreground">
          FY{fyYear} &middot; Configure model assumptions by location and period
        </p>
      </div>

      <div className="flex gap-6">
        {/* Left panel — version list */}
        <div className="w-72 shrink-0 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Versions
            </h2>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowNewForm(true)}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              New Version
            </Button>
          </div>

          {showNewForm && (
            <Card>
              <CardContent className="p-3 space-y-2">
                <Input
                  placeholder="Version name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  autoFocus
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!newName.trim() || createMutation.isPending}
                    onClick={() =>
                      createMutation.mutate({
                        name: newName.trim(),
                        fy_year: fyYear,
                        version_type: "budget",
                      })
                    }
                  >
                    {createMutation.isPending ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Check className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    Create
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setShowNewForm(false);
                      setNewName("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {versionsLoading && (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {versions?.map((v) => (
            <button
              key={v.id}
              onClick={() => setActiveVersionId(v.id)}
              className={`w-full text-left rounded-lg border p-3 transition-colors ${
                v.id === activeVersionId
                  ? "border-primary bg-primary/5 ring-1 ring-primary"
                  : "hover:bg-accent/50"
              }`}
            >
              <div className="font-medium text-sm">{v.name}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-muted-foreground">
                  FY{v.fy_year}
                </span>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                    v.status === "approved"
                      ? "bg-green-100 text-green-800"
                      : v.status === "locked"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-muted text-muted-foreground"
                  }`}
                >
                  {v.status}
                </span>
                <span className="text-xs text-muted-foreground capitalize">
                  {v.version_type}
                </span>
              </div>
            </button>
          ))}

          {versions && versions.length === 0 && !versionsLoading && (
            <div className="rounded-lg border bg-card p-4 text-center text-sm text-muted-foreground">
              No versions for FY{fyYear}. Create one to get started.
            </div>
          )}
        </div>

        {/* Right panel — tabbed editor */}
        <div className="flex-1 min-w-0">
          {!activeVersionId && (
            <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
              Select a budget version to edit assumptions.
            </div>
          )}

          {activeVersionId && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">
                    {activeVersion?.name ?? "Assumptions"}
                  </CardTitle>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleSave}
                      disabled={saveMutation.isPending}
                    >
                      {saveMutation.isPending ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Save className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      Save
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleSaveAndCalculate}
                      disabled={calculating || saveMutation.isPending}
                    >
                      {calculating ? (
                        <>
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                          Calculating...
                        </>
                      ) : (
                        "Save & Calculate"
                      )}
                    </Button>
                  </div>
                </div>
              </CardHeader>

              {/* Tabs */}
              <div className="border-b px-6">
                <div className="flex gap-0 -mb-px overflow-x-auto">
                  {ASSUMPTION_TABS.map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setActiveTab(tab.key)}
                      className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
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

              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-4">
                  {TAB_DESCRIPTIONS[activeTab]}
                </p>

                {assumptionsLoading ? (
                  <div className="flex justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/50">
                          <th className="px-3 py-2 text-left font-medium sticky left-0 bg-muted/50 z-10 min-w-[160px]">
                            {activeTab === "tax_rate" ? "Subsidiary" : "Location"}
                          </th>
                          {MONTHS.map((m) => (
                            <th
                              key={m}
                              className="px-2 py-2 text-center font-medium whitespace-nowrap min-w-[80px]"
                            >
                              {m}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredAssumptionRows.map(({ rowKey, label }) => (
                          <tr key={rowKey} className="border-b last:border-0">
                            <td className="px-3 py-1.5 sticky left-0 bg-background z-10 font-medium whitespace-nowrap">
                              {label}
                            </td>
                            {MONTHS.map((m, mi) => {
                              const mKey = String(mi + 1);
                              const val = localValues[rowKey]?.[mKey] ?? "";
                              return (
                                <td key={m} className="px-1 py-1">
                                  <input
                                    type="text"
                                    inputMode="decimal"
                                    className="w-full rounded border border-input bg-transparent px-2 py-1 text-center text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
                                    value={val}
                                    onChange={(e) =>
                                      updateCell(rowKey, mKey, e.target.value)
                                    }
                                  />
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                        {filteredAssumptionRows.length === 0 && (
                          <tr>
                            <td
                              colSpan={13}
                              className="px-4 py-8 text-center text-muted-foreground"
                            >
                              {activeTab === "tax_rate"
                                ? activeEntities.length === 0
                                  ? "No active subsidiaries. Add entities in Admin."
                                  : "No data to display."
                                : activeLocations.length === 0
                                  ? "No active locations."
                                  : "No data to display."}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
