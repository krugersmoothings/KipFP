import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  ChevronRight,
  ChevronDown,
  Save,
} from "lucide-react";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  DebtFacilityWithSchedule,
  DebtFacilityUpdate,
  BudgetVersion,
} from "@/types/api";

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
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

export default function DebtSchedulePage() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [edits, setEdits] = useState<
    Record<string, Partial<DebtFacilityUpdate>>
  >({});

  const isAdmin = user?.role === "admin";

  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const { data: facilities, isLoading, error, refetch } = useQuery<
    DebtFacilityWithSchedule[]
  >({
    queryKey: ["debt-facilities", activeVersionId],
    queryFn: async () => {
      const res = await api.get(
        `/api/v1/budgets/${activeVersionId}/debt`
      );
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

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleSaveFacility = useCallback(
    (facilityId: string, fac: DebtFacilityWithSchedule) => {
      const editsForFac = edits[facilityId] ?? {};
      const payload: DebtFacilityUpdate = {
        base_rate: editsForFac.base_rate ?? fac.base_rate,
        margin: editsForFac.margin ?? fac.margin,
        monthly_repayment:
          editsForFac.monthly_repayment ?? fac.monthly_repayment,
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

      {facilities && facilities.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No active debt facilities found.
        </div>
      )}

      {facilities && facilities.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Facilities</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-2.5 text-left font-medium sticky left-0 bg-muted/50 z-10 min-w-[250px]">
                      Facility
                    </th>
                    <th className="px-3 py-2.5 text-left font-medium min-w-[120px]">
                      Type
                    </th>
                    <th className="px-3 py-2.5 text-right font-medium min-w-[100px]">
                      Rate
                    </th>
                    <th className="px-3 py-2.5 text-right font-medium min-w-[130px]">
                      Opening Balance
                    </th>
                    <th className="px-3 py-2.5 text-right font-medium min-w-[130px]">
                      Monthly Repay
                    </th>
                    {isAdmin && (
                      <th className="px-3 py-2.5 text-center font-medium min-w-[80px]">
                        Actions
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {facilities.map((fac) => {
                    const isExp = expanded.has(fac.id);
                    const hasSchedule = fac.schedule.length > 0;
                    const facEdits = edits[fac.id] ?? {};
                    const totalRate =
                      (facEdits.base_rate ?? fac.base_rate ?? 0) +
                      (facEdits.margin ?? fac.margin);

                    return (
                      <FacilityRowGroup
                        key={fac.id}
                        fac={fac}
                        isExpanded={isExp}
                        hasSchedule={hasSchedule}
                        isAdmin={isAdmin}
                        totalRate={totalRate}
                        facEdits={facEdits}
                        onToggle={() => toggleExpand(fac.id)}
                        onEditField={(field, value) =>
                          setEdits((prev) => ({
                            ...prev,
                            [fac.id]: {
                              ...(prev[fac.id] ?? {}),
                              [field]: value,
                            },
                          }))
                        }
                        onSave={() => handleSaveFacility(fac.id, fac)}
                        isSaving={updateMutation.isPending}
                      />
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

interface FacilityRowGroupProps {
  fac: DebtFacilityWithSchedule;
  isExpanded: boolean;
  hasSchedule: boolean;
  isAdmin: boolean;
  totalRate: number;
  facEdits: Partial<DebtFacilityUpdate>;
  onToggle: () => void;
  onEditField: (field: keyof DebtFacilityUpdate, value: number | null) => void;
  onSave: () => void;
  isSaving: boolean;
}

function FacilityRowGroup({
  fac,
  isExpanded,
  hasSchedule,
  isAdmin,
  totalRate,
  facEdits,
  onToggle,
  onEditField,
  onSave,
  isSaving,
}: FacilityRowGroupProps) {
  const hasPendingEdits = Object.keys(facEdits).length > 0;

  return (
    <>
      <tr
        className={`border-b ${hasSchedule ? "cursor-pointer hover:bg-accent/50" : ""}`}
        onClick={hasSchedule ? onToggle : undefined}
      >
        <td className="px-4 py-2.5 sticky left-0 bg-background z-10">
          <span className="inline-flex items-center gap-2">
            {hasSchedule && (
              <span className="text-muted-foreground">
                {isExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
              </span>
            )}
            <span>
              <span className="font-medium">{fac.name}</span>
              <span className="ml-2 text-xs text-muted-foreground">
                {fac.code}
              </span>
            </span>
          </span>
        </td>
        <td className="px-3 py-2.5 text-muted-foreground">
          {FACILITY_TYPE_LABELS[fac.facility_type ?? ""] ?? fac.facility_type ?? "-"}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums">
          {isAdmin ? (
            <input
              type="text"
              inputMode="decimal"
              className="w-20 rounded border border-input bg-transparent px-2 py-0.5 text-right text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
              value={
                facEdits.base_rate !== undefined
                  ? String(facEdits.base_rate ?? "")
                  : String(fac.base_rate ?? "")
              }
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                onEditField("base_rate", isNaN(val) ? null : val);
              }}
            />
          ) : (
            fmtRate(totalRate)
          )}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums">
          {fmtAUD(fac.opening_balance)}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums">
          {isAdmin ? (
            <input
              type="text"
              inputMode="decimal"
              className="w-24 rounded border border-input bg-transparent px-2 py-0.5 text-right text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
              value={
                facEdits.monthly_repayment !== undefined
                  ? String(facEdits.monthly_repayment ?? "")
                  : String(fac.monthly_repayment ?? "")
              }
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                onEditField("monthly_repayment", isNaN(val) ? null : val);
              }}
            />
          ) : (
            fmtAUD(fac.monthly_repayment ?? 0)
          )}
        </td>
        {isAdmin && (
          <td className="px-3 py-2.5 text-center">
            {hasPendingEdits && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onSave();
                }}
                disabled={isSaving}
              >
                {isSaving ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
              </Button>
            )}
          </td>
        )}
      </tr>

      {isExpanded &&
        fac.schedule.map((row, idx) => (
          <tr key={idx} className="border-b bg-accent/20">
            <td className="px-4 py-1.5 pl-10 sticky left-0 bg-accent/20 z-10 text-xs text-muted-foreground">
              {row.period_label}
            </td>
            <td className="px-3 py-1.5 text-xs text-muted-foreground">
              {fmtRate(row.interest_rate_applied)}
            </td>
            <td className="px-3 py-1.5 text-right tabular-nums text-xs">
              {fmtAUD(row.interest_expense)}
            </td>
            <td className="px-3 py-1.5 text-right tabular-nums text-xs">
              {fmtAUD(row.opening_balance)}
            </td>
            <td className="px-3 py-1.5 text-right tabular-nums text-xs">
              {fmtAUD(row.repayment)}
            </td>
            {/* closing balance on hover label */}
            <td className="px-3 py-1.5 text-right tabular-nums text-xs text-muted-foreground">
              &rarr; {fmtAUD(row.closing_balance)}
            </td>
          </tr>
        ))}
    </>
  );
}
