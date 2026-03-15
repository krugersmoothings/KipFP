import axios from "axios";
import { useAppStore } from "@/stores/app";

// FIX(L1): use env var for base URL instead of hardcoded localhost
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // FIX(L2): use lowercase comparison (axios normalises to lowercase)
  const { includeAasb16 } = useAppStore.getState();
  if (!includeAasb16 && config.method === "get") {
    config.params = { ...config.params, include_aasb16: false };
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // FIX(L4): don't redirect if already on the login page
      if (window.location.pathname !== "/login") {
        localStorage.removeItem("access_token");
        // FIX(L3): also clear the Zustand auth store
        try {
          const { useAuthStore } = await import("@/stores/auth");
          useAuthStore.getState().logout?.();
        } catch {
          // auth store may not be available during startup
        }
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
