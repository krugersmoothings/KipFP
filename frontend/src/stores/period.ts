import { create } from "zustand";

const now = new Date();

interface PeriodState {
  fyYear: number;
  fyMonth: number;
  setFyYear: (year: number) => void;
  setFyMonth: (month: number) => void;
  setPeriod: (year: number, month: number) => void;
}

export const usePeriodStore = create<PeriodState>((set) => ({
  fyYear: now.getFullYear(),
  fyMonth: now.getMonth() + 1,

  setFyYear: (fyYear) => set({ fyYear }),
  setFyMonth: (fyMonth) => set({ fyMonth }),
  setPeriod: (fyYear, fyMonth) => set({ fyYear, fyMonth }),
}));
