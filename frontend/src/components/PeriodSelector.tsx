import { useMemo } from "react";
import { Lock } from "lucide-react";
import {
  usePeriodStore,
  periodKey,
  parsePeriodKey,
  periodLabel,
  monthRange,
} from "@/stores/period";

export default function PeriodSelector() {
  const {
    fyYear,
    fyMonth,
    setPeriod,
    dataPreparedToFyYear,
    dataPreparedToFyMonth,
    setDataPreparedTo,
  } = usePeriodStore();

  const viewingOptions = useMemo(
    () => monthRange(fyYear - 2, 1, 48),
    [fyYear],
  );

  const closedOptions = useMemo(
    () => monthRange(fyYear - 2, 1, 48),
    [fyYear],
  );

  const viewingValue = periodKey(fyYear, fyMonth);
  const closedValue = periodKey(dataPreparedToFyYear, dataPreparedToFyMonth);
  const closedLabel = periodLabel(dataPreparedToFyYear, dataPreparedToFyMonth);

  return (
    <div className="flex items-center gap-4 text-sm">
      {/* Viewing period — single month picker */}
      <div className="flex items-center gap-1.5">
        <label htmlFor="period-picker" className="text-xs text-muted-foreground whitespace-nowrap">
          Period
        </label>
        <select
          id="period-picker"
          value={viewingValue}
          onChange={(e) => {
            const { fyYear: y, fyMonth: m } = parsePeriodKey(e.target.value);
            setPeriod(y, m);
          }}
          className="rounded-md border bg-background px-2 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {viewingOptions.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Last Closed Month — always-visible control */}
      <div className="flex items-center gap-1.5 border-l pl-4">
        <Lock className="h-3.5 w-3.5 text-emerald-500" />
        <label htmlFor="closed-picker" className="text-xs text-muted-foreground whitespace-nowrap">
          Last Closed
        </label>
        <select
          id="closed-picker"
          value={closedValue}
          onChange={(e) => {
            const { fyYear: y, fyMonth: m } = parsePeriodKey(e.target.value);
            setDataPreparedTo(y, m);
          }}
          className="rounded-md border bg-background px-2 py-1.5 text-sm font-medium text-emerald-700 dark:text-emerald-400 focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {closedOptions.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
        <span className="hidden text-[10px] text-muted-foreground lg:inline">
          ({closedLabel})
        </span>
      </div>
    </div>
  );
}
