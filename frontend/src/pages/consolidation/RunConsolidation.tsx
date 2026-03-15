import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  Plus,
  Trash2,
  Play,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import api from "@/utils/api";
import { usePeriodStore } from "@/stores/period";
import type { ICRuleRead, ICPreviewRow, EntityRead } from "@/types/api";

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "balanced")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" /> Balanced
      </span>
    );
  if (status === "within_tolerance")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
        <AlertTriangle className="h-3 w-3" /> Within tolerance
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900/30 dark:text-red-400">
      <XCircle className="h-3 w-3" /> Imbalance
    </span>
  );
}

export default function RunConsolidation() {
  const { fyYear, fyMonth } = usePeriodStore();
  const queryClient = useQueryClient();
  const [showRules, setShowRules] = useState(false);
  const [consolidating, setConsolidating] = useState(false);
  const [consolidateResult, setConsolidateResult] = useState<string | null>(null);
  const [consolidateError, setConsolidateError] = useState<string | null>(null);

  const preview = useQuery<ICPreviewRow[]>({
    queryKey: ["ic-preview", fyYear, fyMonth],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/ic-rules/preview", {
        params: { fy_year: fyYear, fy_month: fyMonth },
      });
      return data;
    },
  });

  const rules = useQuery<ICRuleRead[]>({
    queryKey: ["ic-rules"],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/ic-rules");
      return data;
    },
    enabled: showRules,
  });

  const entities = useQuery<EntityRead[]>({
    queryKey: ["entities-list"],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/entities");
      return data;
    },
    enabled: showRules,
  });

  const handleConsolidate = async () => {
    setConsolidating(true);
    setConsolidateResult(null);
    setConsolidateError(null);
    try {
      const { data } = await api.post(`/api/v1/consolidate/${fyYear}/${fyMonth}`);
      setConsolidateResult(`Consolidation queued — run ID: ${data.consolidation_run_id}`);
      // FIX(M24): poll for completion instead of hardcoded 3s timeout
      const pollInterval = setInterval(async () => {
        try {
          const { data: runs } = await api.get("/api/v1/sync/runs", { params: { limit: 1 } });
          const latest = runs?.[0];
          if (!latest || latest.status !== "running") {
            clearInterval(pollInterval);
            queryClient.invalidateQueries({ queryKey: ["ic-preview"] });
          }
        } catch {
          clearInterval(pollInterval);
          queryClient.invalidateQueries({ queryKey: ["ic-preview"] });
        }
      }, 5000);
      setTimeout(() => clearInterval(pollInterval), 120_000);
    } catch (err: unknown) {
      // FIX(L9): surface actual error details
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setConsolidateError(detail || "Failed to trigger consolidation.");
    } finally {
      setConsolidating(false);
    }
  };

  const hasImbalance = preview.data?.some((r) => r.status === "imbalance");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Run Consolidation</h1>
        <p className="text-muted-foreground">
          Review intercompany eliminations and run consolidation for FY{fyYear} M
          {String(fyMonth).padStart(2, "0")}.
        </p>
      </div>

      {/* IC Elimination Preview */}
      <Card>
        <CardHeader>
          <CardTitle>IC Elimination Preview</CardTitle>
          <CardDescription>
            Intercompany balances for the selected period. Both sides should net to zero.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {preview.isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}
          {preview.isError && (
            <p className="text-sm text-destructive">Failed to load IC preview.</p>
          )}
          {preview.data && preview.data.length === 0 && (
            <p className="py-4 text-sm text-muted-foreground">
              No active IC elimination rules. Add rules below to start tracking intercompany balances.
            </p>
          )}
          {preview.data && preview.data.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <th className="pb-2 pr-4">Rule</th>
                    <th className="pb-2 pr-4 text-right">Side A</th>
                    <th className="pb-2 pr-4 text-right">Side B</th>
                    <th className="pb-2 pr-4 text-right">Net</th>
                    <th className="pb-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.data.map((row) => (
                    <tr key={row.rule_id} className="border-b last:border-0">
                      <td className="py-3 pr-4">
                        <div className="font-medium">{row.label}</div>
                        <div className="text-xs text-muted-foreground">
                          {row.entity_a_code}:{row.account_code_a} vs{" "}
                          {row.entity_b_code}:{row.account_code_b}
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-right tabular-nums">
                        <div>{fmtAUD(row.balance_a)}</div>
                        <div className="text-xs text-muted-foreground">{row.entity_a_code}</div>
                      </td>
                      <td className="py-3 pr-4 text-right tabular-nums">
                        <div>{fmtAUD(row.balance_b)}</div>
                        <div className="text-xs text-muted-foreground">{row.entity_b_code}</div>
                      </td>
                      <td className={`py-3 pr-4 text-right tabular-nums font-medium ${row.status === "imbalance" ? "text-red-600" : ""}`}>
                        {fmtAUD(row.net)}
                      </td>
                      <td className="py-3">
                        <StatusBadge status={row.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Consolidation Action */}
      <Card>
        <CardContent className="flex items-center gap-4 pt-6">
          <Button onClick={handleConsolidate} disabled={consolidating} size="lg">
            {consolidating ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Run Consolidation
          </Button>
          {hasImbalance && (
            <span className="text-sm text-amber-600">
              <AlertTriangle className="mr-1 inline h-4 w-4" />
              IC imbalances detected — consolidation will proceed but alerts will be logged.
            </span>
          )}
          {consolidateResult && <p className="text-sm text-emerald-700">{consolidateResult}</p>}
          {consolidateError && <p className="text-sm text-destructive">{consolidateError}</p>}
        </CardContent>
      </Card>

      {/* Manage Rules (collapsible) */}
      <Card>
        <CardHeader
          className="cursor-pointer select-none"
          onClick={() => setShowRules(!showRules)}
        >
          <div className="flex items-center gap-2">
            {showRules ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <CardTitle className="text-base">Manage IC Rules</CardTitle>
          </div>
          <CardDescription>
            Define which accounts in which entities should net to zero on consolidation.
          </CardDescription>
        </CardHeader>
        {showRules && (
          <CardContent className="space-y-4">
            <RulesManager
              rules={rules.data ?? []}
              entities={entities.data ?? []}
              isLoading={rules.isLoading || entities.isLoading}
            />
          </CardContent>
        )}
      </Card>
    </div>
  );
}

// ── Rules Manager ─────────────────────────────────────────────────────────────

interface RulesManagerProps {
  rules: ICRuleRead[];
  entities: EntityRead[];
  isLoading: boolean;
}

function RulesManager({ rules, entities, isLoading }: RulesManagerProps) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({
    label: "",
    entity_a_id: "",
    account_code_a: "",
    entity_b_id: "",
    account_code_b: "",
    tolerance: "10.00",
  });

  const createMutation = useMutation({
    mutationFn: async (payload: typeof form) => {
      await api.post("/api/v1/ic-rules", {
        label: payload.label,
        entity_a_id: payload.entity_a_id,
        account_code_a: payload.account_code_a,
        entity_b_id: payload.entity_b_id,
        account_code_b: payload.account_code_b,
        tolerance: parseFloat(payload.tolerance) || 10,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ic-rules"] });
      queryClient.invalidateQueries({ queryKey: ["ic-preview"] });
      setAdding(false);
      setForm({ label: "", entity_a_id: "", account_code_a: "", entity_b_id: "", account_code_b: "", tolerance: "10.00" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (ruleId: string) => {
      await api.delete(`/api/v1/ic-rules/${ruleId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ic-rules"] });
      queryClient.invalidateQueries({ queryKey: ["ic-preview"] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) => {
      await api.put(`/api/v1/ic-rules/${id}`, { is_active });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ic-rules"] });
      queryClient.invalidateQueries({ queryKey: ["ic-preview"] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const activeEntities = entities.filter((e) => e.is_active);

  return (
    <div className="space-y-4">
      {rules.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
              <th className="pb-2 pr-3">Label</th>
              <th className="pb-2 pr-3">Side A</th>
              <th className="pb-2 pr-3">Side B</th>
              <th className="pb-2 pr-3 text-right">Tolerance</th>
              <th className="pb-2 pr-3">Active</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="py-2 pr-3 font-medium">{r.label}</td>
                <td className="py-2 pr-3 text-xs">
                  {r.entity_a_code}:{r.account_code_a}
                </td>
                <td className="py-2 pr-3 text-xs">
                  {r.entity_b_code}:{r.account_code_b}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">{r.tolerance.toFixed(2)}</td>
                <td className="py-2 pr-3">
                  <button
                    onClick={() => toggleMutation.mutate({ id: r.id, is_active: !r.is_active })}
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      r.is_active
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                    }`}
                  >
                    {r.is_active ? "On" : "Off"}
                  </button>
                </td>
                <td className="py-2">
                  <button
                    onClick={() => {
                      if (confirm(`Delete rule "${r.label}"?`)) deleteMutation.mutate(r.id);
                    }}
                    className="rounded p-1 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {rules.length === 0 && !adding && (
        <p className="py-2 text-sm text-muted-foreground">No IC rules configured yet.</p>
      )}

      {!adding && (
        <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
          <Plus className="mr-1 h-3.5 w-3.5" /> Add Rule
        </Button>
      )}

      {adding && (
        <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
          <div className="space-y-1.5">
            <Label>Label</Label>
            <Input
              placeholder="e.g. MC Management Fees"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Entity A</Label>
              <select
                value={form.entity_a_id}
                onChange={(e) => setForm({ ...form, entity_a_id: e.target.value })}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Select entity...</option>
                {activeEntities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.code} — {e.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Account Code A</Label>
              <Input
                placeholder="e.g. Sales"
                value={form.account_code_a}
                onChange={(e) => setForm({ ...form, account_code_a: e.target.value })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Entity B</Label>
              <select
                value={form.entity_b_id}
                onChange={(e) => setForm({ ...form, entity_b_id: e.target.value })}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Select entity...</option>
                {activeEntities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.code} — {e.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Account Code B</Label>
              <Input
                placeholder="e.g. 62300"
                value={form.account_code_b}
                onChange={(e) => setForm({ ...form, account_code_b: e.target.value })}
              />
            </div>
          </div>
          <div className="w-40 space-y-1.5">
            <Label>Tolerance ($)</Label>
            <Input
              type="number"
              step="0.01"
              value={form.tolerance}
              onChange={(e) => setForm({ ...form, tolerance: e.target.value })}
            />
          </div>
          <div className="flex gap-2 pt-1">
            <Button
              size="sm"
              onClick={() => createMutation.mutate(form)}
              disabled={!form.label || !form.entity_a_id || !form.account_code_a || !form.entity_b_id || !form.account_code_b || createMutation.isPending}
            >
              {createMutation.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
              Save Rule
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
