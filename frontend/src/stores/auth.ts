import { create } from "zustand";
import type { User } from "@/types/api";
import api from "@/utils/api";

interface AuthState {
  token: string | null;
  user: User | null;
  setToken: (token: string | null) => void;
  setUser: (user: User | null) => void;
  logout: () => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem("access_token"),
  user: null,

  setToken: (token) => {
    if (token) {
      localStorage.setItem("access_token", token);
    } else {
      localStorage.removeItem("access_token");
    }
    set({ token });
  },

  setUser: (user) => set({ user }),

  logout: () => {
    localStorage.removeItem("access_token");
    set({ token: null, user: null });
  },

  fetchUser: async () => {
    try {
      const { data } = await api.get<User>("/api/v1/auth/me");
      set({ user: data });
    } catch {
      get().logout();
    }
  },
}));
