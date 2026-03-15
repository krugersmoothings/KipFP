import { useQuery } from "@tanstack/react-query";
import { X, ExternalLink, Loader2 } from "lucide-react";
import api from "@/utils/api";
import type { CellClickInfo } from "./FinancialTable";

interface DrillDownEntity {
  entity_id: string | null;
  entity_code: string;
  entity_name: string;
  amount: number;
  source_entity_id: string | null;
  netsuite_url?: string | null;
}

interface Props {
  info: CellClickInfo;
  fyYear: number;
  fyMonth: number;
  onClose: () => void;
}

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
}

export default function DrillDownModal({ info, fyYear, fyMonth, onClose }: Props) {
  const { data, isLoading, error } = useQuery<DrillDownEntity[]>({
    queryKey: ["drilldown", fyYear, fyMonth, info.accountCode],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/consolidated/drilldown", {
        params: {
          fy_year: fyYear,
          fy_month: fyMonth,
          account_code: info.accountCode,
        },
      });
      return data;
    },
  });

  const { data: urls } = useQuery<Record<string, string>>({
    queryKey: ["netsuite-urls", fyYear, fyMonth, info.accountCode],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/entities/netsuite-urls", {
        params: {
          account_code: info.accountCode,
          fy_year: fyYear,
          fy_month: fyMonth,
        },
      });
      return data;
    },
    enabled: !!data && data.length > 0,
  });

  const total = data?.reduce((sum, e) => sum + e.amount, 0) ?? 0;

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg transform bg-background shadow-xl transition-transform">
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b px-6 py-4">
            <div>
              <h2 className="text-lg font-semibold">{info.accountLabel}</h2>
              <p className="text-sm text-muted-foreground">
                {info.period} &middot; {info.accountCode}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-muted-foreground hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
                Failed to load entity breakdown.
              </div>
            )}

            {data && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="pb-2 text-left font-medium">Entity</th>
                    <th className="pb-2 text-right font-medium">Amount</th>
                    <th className="pb-2 w-10" />
                  </tr>
                </thead>
                <tbody>
                  {data.map((entity) => {
                    const nsUrl = urls?.[entity.entity_code];
                    return (
                      <tr
                        key={entity.entity_code}
                        className="border-b last:border-0"
                      >
                        <td className="py-2.5">
                          <div className="font-medium">{entity.entity_code}</div>
                          <div className="text-xs text-muted-foreground">
                            {entity.entity_name}
                          </div>
                        </td>
                        <td
                          className={`py-2.5 text-right tabular-nums ${
                            entity.amount < 0 ? "text-red-600" : ""
                          }`}
                        >
                          {fmtAUD(entity.amount)}
                        </td>
                        <td className="py-2.5 text-center">
                          {nsUrl && (
                            <a
                              href={nsUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center text-muted-foreground hover:text-primary"
                              title="View in NetSuite"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t-2">
                    <td className="py-2.5 font-semibold">Total</td>
                    <td
                      className={`py-2.5 text-right font-semibold tabular-nums ${
                        total < 0 ? "text-red-600" : ""
                      }`}
                    >
                      {fmtAUD(total)}
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            )}

            {data && data.length === 0 && (
              <div className="py-8 text-center text-muted-foreground">
                No entity breakdown available for this cell.
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
