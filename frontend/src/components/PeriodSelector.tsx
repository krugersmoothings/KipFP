import { useMemo } from "react";
import {
  usePeriodStore,
  periodKey,
  parsePeriodKey,
  monthRange,
} from "@/stores/period";

export default function PeriodSelector() {
  const { fyYear, fyMonth, setPeriod } = usePeriodStore();

  const options = useMemo(
    () => monthRange(fyYear - 2, 1, 48),
    [fyYear],
  );

  const value = periodKey(fyYear, fyMonth);

  return (
    <div className="flex items-center gap-1.5 text-sm">
      <label htmlFor="period-picker" className="text-xs text-muted-foreground whitespace-nowrap">
        Period
      </label>
      <select
        id="period-picker"
        value={value}
        onChange={(e) => {
          const { fyYear: y, fyMonth: m } = parsePeriodKey(e.target.value);
          setPeriod(y, m);
        }}
        className="rounded-md border bg-background px-2 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {options.map((opt) => (
          <option key={opt.key} value={opt.key}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
