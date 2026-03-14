import { usePeriodStore } from "@/stores/period";

const FY_MONTHS = [
  { label: "Jul", value: 1 },
  { label: "Aug", value: 2 },
  { label: "Sep", value: 3 },
  { label: "Oct", value: 4 },
  { label: "Nov", value: 5 },
  { label: "Dec", value: 6 },
  { label: "Jan", value: 7 },
  { label: "Feb", value: 8 },
  { label: "Mar", value: 9 },
  { label: "Apr", value: 10 },
  { label: "May", value: 11 },
  { label: "Jun", value: 12 },
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
        {FY_MONTHS.map(({ label, value }) => (
          <option key={value} value={value}>
            M{String(value).padStart(2, "0")} {label}
          </option>
        ))}
      </select>
    </div>
  );
}
