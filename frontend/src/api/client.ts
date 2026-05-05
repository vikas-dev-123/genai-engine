import axios, { type AxiosRequestConfig } from "axios";

import { getApiBasePath } from "../env";
import { useAuthStore } from "../store/authStore";

type RetryConfig = AxiosRequestConfig & { _retry?: boolean };

const apiClient = axios.create({
  baseURL: getApiBasePath(),
  timeout: 30000,
});

let refreshInFlight: Promise<string | null> | null = null;

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || !error.config) {
      return Promise.reject(error);
    }
    const status = error.response?.status;
    const originalRequest = error.config as RetryConfig;
    if (status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        if (!refreshInFlight) {
          refreshInFlight = useAuthStore
            .getState()
            .refreshAccessToken()
            .finally(() => {
              refreshInFlight = null;
            });
        }
        const token = await refreshInFlight;
        if (token) {
          originalRequest.headers = originalRequest.headers ?? {};
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return apiClient(originalRequest);
        }
      } catch {
        /* fall through to logout */
      }
      useAuthStore.getState().logout();
      window.location.assign("/");
      return Promise.reject(error);
    }
    return Promise.reject(error);
  },
);

export default apiClient;
