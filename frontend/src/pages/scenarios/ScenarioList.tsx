import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Loader2, Plus, GitBranch, Clock, CheckCircle2 } from "lucide-react";
import api from "@/utils/api";
import { useBudgetStore } from "@/stores/budget";
import { usePeriodStore } from "@/stores/period";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { BudgetVersion, ScenarioRead } from "@/types/api";

export default function ScenarioList() {
  const { fyYear } = usePeriodStore();
  const { activeVersionId } = useBudgetStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const { data: versions } = useQuery<BudgetVersion[]>({
    queryKey: ["budget-versions", fyYear],
    queryFn: async () => {
      const res = await api.get("/api/v1/budgets/", { params: { fy_year: fyYear } });
      return res.data;
    },
  });

  const { data: scenarios, isLoading } = useQuery<ScenarioRead[]>({
    queryKey: ["scenarios", activeVersionId],
    queryFn: async () => {
      const res = await api.get("/api/v1/scenarios/", {
        params: { version_id: activeVersionId },
      });
      return res.data;
    },
    enabled: !!activeVersionId,
  });

  const createMutation = useMutation({
    mutationFn: async (name: string) => {
      setCreating(true);
      const res = await api.post("/api/v1/scenarios/", {
        name,
        base_version_id: activeVersionId,
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenarios"] });
      setShowCreate(false);
      setNewName("");
      setCreating(false);
    },
    onError: () => setCreating(false),
  });

  const activeVersion = versions?.find((v) => v.id === activeVersionId);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Scenario Manager</h1>
          <p className="text-muted-foreground">
            FY{fyYear}
            {activeVersion && <> &middot; Base: {activeVersion.name}</>}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/scenarios/compare")}
            disabled={!scenarios || scenarios.length === 0}
          >
            Compare Scenarios
          </Button>
          <Button size="sm" onClick={() => setShowCreate(true)} disabled={!activeVersionId}>
            <Plus className="mr-2 h-4 w-4" />
            New Scenario
          </Button>
        </div>
      </div>

      {!activeVersionId && (
        <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
          Select a budget version on the Assumptions page first.
        </div>
      )}

      {showCreate && (
        <Card className="p-4">
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="text-sm font-medium mb-1 block">Scenario Name</label>
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Upside Case, Conservative..."
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newName.trim()) createMutation.mutate(newName.trim());
                }}
              />
            </div>
            <Button
              size="sm"
              onClick={() => newName.trim() && createMutation.mutate(newName.trim())}
              disabled={!newName.trim() || creating}
            >
              {creating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create & Calculate
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setShowCreate(false);
                setNewName("");
              }}
            >
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {scenarios && scenarios.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No scenarios yet. Create one to start comparing different assumptions.
        </div>
      )}

      {scenarios && scenarios.length > 0 && (
        <div className="grid gap-3">
          {scenarios.map((s) => (
            <Card
              key={s.id}
              className="flex items-center justify-between p-4 hover:bg-accent/50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <GitBranch className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="font-medium">{s.name}</p>
                  <p className="text-xs text-muted-foreground">
                    Created {new Date(s.created_at).toLocaleDateString()}
                    {s.description && <> &middot; {s.description}</>}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    s.status === "draft"
                      ? "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                      : "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                  }`}
                >
                  {s.status === "draft" ? (
                    <Clock className="h-3 w-3" />
                  ) : (
                    <CheckCircle2 className="h-3 w-3" />
                  )}
                  {s.status}
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
