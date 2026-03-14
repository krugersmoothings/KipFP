import { useQuery } from "@tanstack/react-query";
import api from "@/utils/api";
import { usePeriodStore } from "@/stores/period";
import type { ConsolidatedLineItem } from "@/types/api";

export default function IncomeStatement() {
  const { fyYear, fyMonth } = usePeriodStore();

  const { data, isLoading, error } = useQuery<ConsolidatedLineItem[]>({
    queryKey: ["consolidated-is", fyYear, fyMonth],
    queryFn: async () => {
      const res = await api.get("/api/v1/consolidated/is", {
        params: { fy_year: fyYear, fy_month: fyMonth },
      });
      return res.data;
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Income Statement</h1>
        <p className="text-muted-foreground">
          Consolidated income statement across all entities.
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          Loading...
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Failed to load income statement data.</p>
          <p className="mt-1 text-xs opacity-80">
            {(error as any)?.response?.status && `${(error as any).response.status}: `}
            {(error as any)?.response?.data?.detail ?? error.message}
          </p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">Account</th>
                <th className="px-4 py-3 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr
                  key={row.account_code}
                  className={`border-b last:border-0 ${
                    row.is_subtotal ? "bg-muted/30 font-semibold" : ""
                  }`}
                >
                  <td className="px-4 py-2">
                    <span className="mr-2 text-muted-foreground">
                      {row.account_code}
                    </span>
                    {row.account_name}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {row.amount.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          No income statement data available. Run a consolidation first.
        </div>
      )}
    </div>
  );
}
