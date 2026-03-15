import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, AlertTriangle, Search, ShieldCheck } from "lucide-react";
import api from "@/utils/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import type {
  SourceAccountRead,
  TargetAccountRead,
  AccountMappingRead,
  ValidationResult,
} from "@/types/api";

export default function CoaMapping() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<SourceAccountRead | null>(null);
  const [filter, setFilter] = useState("");
  const [targetId, setTargetId] = useState("");
  const [multiplier, setMultiplier] = useState("1.0");
  const [effectiveFrom, setEffectiveFrom] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [notes, setNotes] = useState("");
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);

  const { data: sourceAccounts, isLoading: loadingSources } = useQuery<SourceAccountRead[]>({
    queryKey: ["coa-source-accounts"],
    queryFn: async () => {
      const res = await api.get("/api/v1/coa/source-accounts");
      return res.data;
    },
  });

  const { data: targetAccounts } = useQuery<TargetAccountRead[]>({
    queryKey: ["coa-target-accounts"],
    queryFn: async () => {
      const res = await api.get("/api/v1/coa/target-accounts");
      return res.data;
    },
  });

  const { data: currentMapping, isLoading: loadingMapping } = useQuery<AccountMappingRead | null>({
    queryKey: ["coa-mapping", selected?.entity_id, selected?.source_account_code],
    queryFn: async () => {
      const res = await api.get(
        `/api/v1/coa/mappings/${selected!.entity_id}/${encodeURIComponent(selected!.source_account_code)}`
      );
      return res.data;
    },
    enabled: !!selected,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!selected) return;
      await api.put("/api/v1/coa/mappings", {
        entity_id: selected.entity_id,
        source_account_code: selected.source_account_code,
        source_account_name: selected.source_account_name,
        target_account_id: targetId,
        multiplier: parseFloat(multiplier) || 1.0,
        effective_from: effectiveFrom,
        notes: notes || null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["coa-source-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["coa-mapping"] });
    },
  });

  const handleValidate = async () => {
    setValidating(true);
    try {
      const res = await api.post("/api/v1/coa/validate");
      setValidationResult(res.data);
    } catch {
      // FIX(M35): surface validation errors
      alert("Validation failed — please try again.");
    } finally {
      setValidating(false);
    }
  };

  const handleSelect = (acct: SourceAccountRead) => {
    setSelected(acct);
    // FIX(M34): reset effectiveFrom when selecting a new source account
    setTargetId("");
    setMultiplier("1.0");
    setEffectiveFrom(null);
    setNotes("");
  };

  useEffect(() => {
    if (currentMapping && currentMapping.target_account_id) {
      setTargetId(currentMapping.target_account_id);
      setMultiplier(String(currentMapping.multiplier));
      setEffectiveFrom(currentMapping.effective_from);
      setNotes(currentMapping.notes || "");
    }
  }, [currentMapping]);

  const filtered = sourceAccounts?.filter((a) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return (
      a.source_account_code.toLowerCase().includes(q) ||
      (a.source_account_name?.toLowerCase().includes(q) ?? false) ||
      a.entity_code.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Chart of Accounts Mapping</h1>
          <p className="text-muted-foreground">
            Map source system accounts to the group chart of accounts
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleValidate}
          disabled={validating}
        >
          {validating ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <ShieldCheck className="mr-2 h-4 w-4" />
          )}
          Validate All Mappings
        </Button>
      </div>

      {validationResult && (
        <Card className="p-4">
          <div className="flex items-center gap-4 text-sm">
            <span>
              <strong>{validationResult.total_source_accounts}</strong> total accounts
            </span>
            <span className="text-green-600">
              <CheckCircle2 className="inline h-4 w-4 mr-1" />
              {validationResult.mapped_count} mapped
            </span>
            <span className={validationResult.unmapped_count > 0 ? "text-amber-600" : "text-green-600"}>
              <AlertTriangle className="inline h-4 w-4 mr-1" />
              {validationResult.unmapped_count} unmapped
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => setValidationResult(null)}
            >
              Dismiss
            </Button>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Source accounts list */}
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Filter accounts..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>

          {loadingSources && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}

          <div className="max-h-[calc(100vh-320px)] overflow-y-auto rounded-lg border divide-y">
            {filtered?.map((acct) => (
              <button
                key={`${acct.entity_id}-${acct.source_account_code}`}
                className={`w-full text-left px-4 py-3 hover:bg-accent/50 transition-colors ${
                  selected?.entity_id === acct.entity_id &&
                  selected?.source_account_code === acct.source_account_code
                    ? "bg-accent"
                    : ""
                } ${!acct.is_mapped ? "border-l-4 border-l-amber-400" : ""}`}
                onClick={() => handleSelect(acct)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs text-muted-foreground mr-2">
                      {acct.entity_code}
                    </span>
                    <span className="font-mono text-sm">{acct.source_account_code}</span>
                  </div>
                  <span
                    className={`text-xs rounded-full px-2 py-0.5 ${
                      acct.is_mapped
                        ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                        : "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
                    }`}
                  >
                    {acct.is_mapped ? "Mapped" : "Unmapped"}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground truncate mt-0.5">
                  {acct.source_account_name}
                </p>
                {acct.is_mapped && acct.target_account_name && (
                  <p className="text-xs text-green-600 dark:text-green-400 mt-0.5">
                    → {acct.target_account_code} {acct.target_account_name}
                  </p>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Mapping editor */}
        <div>
          {!selected && (
            <div className="rounded-lg border bg-card p-12 text-center text-muted-foreground">
              Select a source account from the list to view or edit its mapping.
            </div>
          )}

          {selected && (
            <Card className="p-6 space-y-4">
              <div>
                <h3 className="font-semibold">Source Account</h3>
                <p className="text-sm text-muted-foreground">{selected.entity_code}</p>
                <p className="font-mono">{selected.source_account_code}</p>
                <p className="text-sm">{selected.source_account_name}</p>
              </div>

              {loadingMapping && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}

              {!loadingMapping && (
                <>
                  <div>
                    <label className="text-sm font-medium mb-1 block">Target Group Account</label>
                    <select
                      className="w-full rounded border px-3 py-2 text-sm bg-background"
                      value={targetId}
                      onChange={(e) => setTargetId(e.target.value)}
                    >
                      <option value="">— Select target account —</option>
                      {targetAccounts?.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.code} — {t.name} ({t.statement?.toUpperCase()})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm font-medium mb-1 block">Multiplier</label>
                      <Input
                        type="number"
                        step="0.0001"
                        value={multiplier}
                        onChange={(e) => setMultiplier(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-1 block">Effective From</label>
                      <Input
                        type="date"
                        value={effectiveFrom}
                        onChange={(e) => setEffectiveFrom(e.target.value)}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-sm font-medium mb-1 block">Notes</label>
                    <textarea
                      className="w-full rounded border px-3 py-2 text-sm bg-background resize-none"
                      rows={3}
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Optional notes about this mapping..."
                    />
                  </div>

                  <Button
                    className="w-full"
                    disabled={!targetId || saveMutation.isPending}
                    onClick={() => saveMutation.mutate()}
                  >
                    {saveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Save Mapping
                  </Button>

                  {saveMutation.isSuccess && (
                    <p className="text-sm text-green-600 flex items-center gap-1">
                      <CheckCircle2 className="h-4 w-4" /> Mapping saved successfully.
                    </p>
                  )}
                </>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
