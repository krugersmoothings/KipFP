import { create } from "zustand";

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const now = new Date();
const calMonth = now.getMonth() + 1; // 1-12
const calYear = now.getFullYear();

// Australian FY: Jul=M01 … Jun=M12
const defaultFyMonth = calMonth >= 7 ? calMonth - 6 : calMonth + 6;
const defaultFyYear = calMonth >= 7 ? calYear + 1 : calYear;

/** Convert FY year + FY month (1=Jul..12=Jun) to a calendar month (1-12) */
export function fyToCalMonth(fyMonth: number): number {
  return ((fyMonth + 5) % 12) + 1;
}

/** Convert FY year + FY month to a calendar year */
export function fyToCalYear(fyYear: number, fyMonth: number): number {
  return fyMonth <= 6 ? fyYear - 1 : fyYear;
}

/** Convert calendar year + calendar month to FY year */
export function calToFyYear(calYear: number, calMonth: number): number {
  return calMonth >= 7 ? calYear + 1 : calYear;
}

/** Convert calendar month (1-12) to FY month (1=Jul..12=Jun) */
export function calToFyMonth(calMonth: number): number {
  return calMonth >= 7 ? calMonth - 6 : calMonth + 6;
}

/** "Jan-26" style label from FY year + FY month */
export function periodLabel(fyYear: number, fyMonth: number): string {
  const cm = fyToCalMonth(fyMonth);
  const cy = fyToCalYear(fyYear, fyMonth);
  return `${MONTH_ABBR[cm - 1]}-${String(cy).slice(-2)}`;
}

/** Composite key "2026|7" for use as select option values */
export function periodKey(fyYear: number, fyMonth: number): string {
  return `${fyYear}|${fyMonth}`;
}

/** Parse composite key back to { fyYear, fyMonth } */
export function parsePeriodKey(key: string): { fyYear: number; fyMonth: number } {
  const [y, m] = key.split("|").map(Number);
  return { fyYear: y, fyMonth: m };
}

/** Generate an array of { key, label } for a range of months */
export function monthRange(
  startFyYear: number,
  startFyMonth: number,
  count: number,
): { key: string; label: string }[] {
  const result: { key: string; label: string }[] = [];
  let fy = startFyYear;
  let fm = startFyMonth;
  for (let i = 0; i < count; i++) {
    result.push({ key: periodKey(fy, fm), label: periodLabel(fy, fm) });
    fm++;
    if (fm > 12) {
      fm = 1;
      fy++;
    }
  }
  return result;
}

function loadPreparedTo(): { year: number; month: number } {
  try {
    const raw = localStorage.getItem("kip_data_prepared_to");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.year && parsed.month) return parsed;
    }
  } catch { /* ignore */ }
  return { year: defaultFyYear, month: defaultFyMonth };
}

const savedPreparedTo = loadPreparedTo();

interface PeriodState {
  fyYear: number;
  fyMonth: number;
  dataPreparedToFyYear: number;
  dataPreparedToFyMonth: number;
  setFyYear: (year: number) => void;
  setFyMonth: (month: number) => void;
  setPeriod: (year: number, month: number) => void;
  setDataPreparedTo: (year: number, month: number) => void;
}

export const usePeriodStore = create<PeriodState>((set) => ({
  fyYear: defaultFyYear,
  fyMonth: defaultFyMonth,
  dataPreparedToFyYear: savedPreparedTo.year,
  dataPreparedToFyMonth: savedPreparedTo.month,

  setFyYear: (fyYear) => set({ fyYear }),
  setFyMonth: (fyMonth) => set({ fyMonth }),
  setPeriod: (fyYear, fyMonth) => {
    localStorage.setItem("kip_data_prepared_to", JSON.stringify({ year: fyYear, month: fyMonth }));
    set({ fyYear, fyMonth, dataPreparedToFyYear: fyYear, dataPreparedToFyMonth: fyMonth });
  },
  setDataPreparedTo: (year, month) => {
    localStorage.setItem("kip_data_prepared_to", JSON.stringify({ year, month }));
    set({ dataPreparedToFyYear: year, dataPreparedToFyMonth: month });
  },
}));
