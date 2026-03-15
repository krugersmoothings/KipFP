import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AppState {
  includeAasb16: boolean;
  setIncludeAasb16: (value: boolean) => void;
  toggleAasb16: () => void;
}

// FIX(M43): persist AASB16 toggle across page refreshes
export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      includeAasb16: true,
      setIncludeAasb16: (includeAasb16) => set({ includeAasb16 }),
      toggleAasb16: () => set((s) => ({ includeAasb16: !s.includeAasb16 })),
    }),
    { name: "kip-app-settings" },
  ),
);
