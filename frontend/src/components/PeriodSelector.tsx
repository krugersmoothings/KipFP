import { usePeriodStore } from "@/stores/period";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export default function PeriodSelector() {
  const { fyYear, fyMonth, setFyYear, setFyMonth } = usePeriodStore();

  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor="period-year" className="sr-only">
        Financial Year
      </label>
      <select
        id="period-year"
        value={fyYear}
        onChange={(e) => setFyYear(Number(e.target.value))}
        className="rounded-md border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {Array.from({ length: 6 }, (_, i) => fyYear - 2 + i).map((y) => (
          <option key={y} value={y}>
            FY {y}
          </option>
        ))}
      </select>

      <label htmlFor="period-month" className="sr-only">
        Month
      </label>
      <select
        id="period-month"
        value={fyMonth}
        onChange={(e) => setFyMonth(Number(e.target.value))}
        className="rounded-md border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {MONTHS.map((label, i) => (
          <option key={i + 1} value={i + 1}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );
}
