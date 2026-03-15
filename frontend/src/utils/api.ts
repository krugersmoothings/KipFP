import axios from "axios";
import { useAppStore } from "@/stores/app";

const api = axios.create({
  baseURL: "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // FIX(C8): only inject include_aasb16 as a query param on GET — spreading into POST/PUT bodies corrupts FormData and arrays
  const { includeAasb16 } = useAppStore.getState();
  if (!includeAasb16 && config.method?.toLowerCase() === "get") {
    config.params = { ...config.params, include_aasb16: false };
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
