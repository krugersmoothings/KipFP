import { create } from "zustand";

interface BudgetState {
  activeVersionId: string | null;
  setActiveVersionId: (id: string | null) => void;
}

export const useBudgetStore = create<BudgetState>((set) => ({
  activeVersionId: null,
  setActiveVersionId: (activeVersionId) => set({ activeVersionId }),
}));
