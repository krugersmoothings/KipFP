import { create } from "zustand";

const now = new Date();
const calMonth = now.getMonth() + 1; // 1-12
const calYear = now.getFullYear();

// Australian FY: Jul=M01 … Jun=M12
const defaultFyMonth = calMonth >= 7 ? calMonth - 6 : calMonth + 6;
const defaultFyYear = calMonth >= 7 ? calYear + 1 : calYear;

interface PeriodState {
  fyYear: number;
  fyMonth: number;
  setFyYear: (year: number) => void;
  setFyMonth: (month: number) => void;
  setPeriod: (year: number, month: number) => void;
}

export const usePeriodStore = create<PeriodState>((set) => ({
  fyYear: defaultFyYear,
  fyMonth: defaultFyMonth,

  setFyYear: (fyYear) => set({ fyYear }),
  setFyMonth: (fyMonth) => set({ fyMonth }),
  setPeriod: (fyYear, fyMonth) => set({ fyYear, fyMonth }),
}));
