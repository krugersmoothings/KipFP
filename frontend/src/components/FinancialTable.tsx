import { useState, useCallback } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import type { FinancialRow } from "@/types/api";

export interface CellClickInfo {
  accountCode: string;
  accountLabel: string;
  period: string;
  value: number;
}

interface Props {
  rows: FinancialRow[];
  periods: string[];
  showEntityBreakdown?: boolean;
  highlightVariance?: boolean;
  compact?: boolean;
  lastActualMonth?: number;
  onCellClick?: (info: CellClickInfo) => void;
}

function fmtAUD(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("en-AU");
  return n < 0 ? `(${formatted})` : formatted;
}

function fmtPct(n: number): string {
  const abs = Math.abs(n);
  const formatted = abs.toFixed(1) + "%";
  return n < 0 ? `(${formatted})` : formatted;
}

const SUMMARY_COLUMNS = new Set(["YTD", "YTD Budget", "Var %"]);

const MONTH_ABBR = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"];

export default function FinancialTable({
  rows,
  periods,
  showEntityBreakdown = false,
  highlightVariance = false,
  compact = false,
  lastActualMonth,
  onCellClick,
}: Props) {
  const forecastPeriods = new Set<string>();
  if (lastActualMonth != null) {
    for (let m = lastActualMonth; m < 12; m++) {
      forecastPeriods.add(MONTH_ABBR[m]);
    }
  }
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = useCallback((code: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  const cellPad = compact ? "px-3 py-1" : "px-4 py-2";
  const headerPad = compact ? "px-3 py-2" : "px-4 py-3";

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50">
            <th
              className={`${headerPad} text-left font-medium sticky left-0 bg-muted/50 z-10 min-w-[220px]`}
            >
              Account
            </th>
            {periods.map((p) => {
              const isForecast = lastActualMonth != null && forecastPeriods.has(p.split("-")[0]);
              const isSummary = SUMMARY_COLUMNS.has(p);
              return (
                <th
                  key={p}
                  className={`${headerPad} text-right font-medium whitespace-nowrap min-w-[100px] ${
                    isForecast ? "text-blue-600 dark:text-blue-400" : ""
                  } ${isSummary ? "bg-muted/80 border-l" : ""}`}
                >
                  {p}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            if (row.is_section_header) {
              return (
                <tr key={`sh-${idx}`} className="border-b">
                  <td
                    colSpan={periods.length + 1}
                    className={`${cellPad} pt-4 font-semibold text-primary tracking-wide text-xs uppercase sticky left-0 bg-background z-10`}
                  >
                    {row.label}
                  </td>
                </tr>
              );
            }

            const isExpanded = expanded.has(row.account_code);
            const hasBreakdown =
              showEntityBreakdown &&
              !row.is_subtotal &&
              Object.keys(row.entity_breakdown).length > 0;

            return (
              <RowGroup
                key={row.account_code || `row-${idx}`}
                row={row}
                periods={periods}
                isExpanded={isExpanded}
                hasBreakdown={hasBreakdown}
                onToggle={toggle}
                highlightVariance={highlightVariance}
                cellPad={cellPad}
                onCellClick={onCellClick}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Individual row + optional entity expansion ──────────────────────────

interface RowGroupProps {
  row: FinancialRow;
  periods: string[];
  isExpanded: boolean;
  hasBreakdown: boolean;
  onToggle: (code: string) => void;
  highlightVariance: boolean;
  cellPad: string;
  onCellClick?: (info: CellClickInfo) => void;
}

function RowGroup({
  row,
  periods,
  isExpanded,
  hasBreakdown,
  onToggle,
  highlightVariance,
  cellPad,
  onCellClick,
}: RowGroupProps) {
  const subtotalCls = row.is_subtotal
    ? "bg-muted/30 font-semibold border-t"
    : "";
  const indent = row.indent_level > 0 ? "pl-6" : "";

  const entityCodes = Object.keys(row.entity_breakdown).sort();

  const clickable = !!onCellClick && !row.is_subtotal && !!row.account_code;

  return (
    <>
      <tr
        className={`border-b last:border-0 ${subtotalCls} ${
          hasBreakdown ? "cursor-pointer hover:bg-accent/50" : ""
        }`}
        onClick={hasBreakdown ? () => onToggle(row.account_code) : undefined}
      >
        <td
          className={`${cellPad} sticky left-0 bg-background z-10 ${indent} whitespace-nowrap`}
        >
          <span className="inline-flex items-center gap-1">
            {hasBreakdown && (
              <span className="text-muted-foreground">
                {isExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
              </span>
            )}
            {!row.is_subtotal && (
              <span className="mr-2 text-muted-foreground text-xs">
                {row.account_code}
              </span>
            )}
            {row.label}
          </span>
        </td>
        {periods.map((p) => {
          const val = row.values[p] ?? 0;
          const isPct = p === "Var %";
          const isSummary = SUMMARY_COLUMNS.has(p);
          const colorCls = isPct
            ? val < 0 ? "text-red-600" : val > 0 ? "text-emerald-600" : ""
            : val < 0 && highlightVariance ? "text-red-600" : "";
          return (
            <td
              key={p}
              className={`${cellPad} text-right tabular-nums whitespace-nowrap ${colorCls} ${
                isSummary ? "bg-muted/30 border-l" : ""
              } ${clickable && !isPct ? "cursor-pointer hover:underline hover:text-primary" : ""}`}
              onClick={
                clickable && !isPct
                  ? (e) => {
                      e.stopPropagation();
                      onCellClick({
                        accountCode: row.account_code,
                        accountLabel: row.label,
                        period: p,
                        value: val,
                      });
                    }
                  : undefined
              }
            >
              {isPct ? fmtPct(val) : fmtAUD(val)}
            </td>
          );
        })}
      </tr>

      {isExpanded &&
        entityCodes.map((ecode) => (
          <tr key={`${row.account_code}-${ecode}`} className="border-b bg-accent/20">
            <td
              className={`${cellPad} pl-10 sticky left-0 bg-accent/20 z-10 text-muted-foreground text-xs`}
            >
              {ecode}
            </td>
            {periods.map((p) => {
              const isPct = p === "Var %";
              const isSummary = SUMMARY_COLUMNS.has(p);
              if (isPct) {
                return <td key={p} className={`${cellPad} border-l bg-muted/30`} />;
              }
              const val = row.entity_breakdown[ecode]?.[p] ?? 0;
              return (
                <td
                  key={p}
                  className={`${cellPad} text-right tabular-nums text-muted-foreground text-xs ${
                    val < 0 ? "text-red-500" : ""
                  } ${isSummary ? "bg-muted/30 border-l" : ""}`}
                >
                  {fmtAUD(val)}
                </td>
              );
            })}
          </tr>
        ))}
    </>
  );
}
