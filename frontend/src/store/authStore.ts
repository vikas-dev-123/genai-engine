import { create } from "zustand";

import {
  getMe,
  login as loginApi,
  refreshToken as refreshTokenApi,
  register as registerApi,
} from "../api/auth";
import type { User } from "../types";

const REFRESH_KEY = "jarvis_refresh_token";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  loadUser: () => Promise<void>;
  refreshAccessToken: () => Promise<string | null>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  isLoading: true,

  login: async (email, password) => {
    const res = await loginApi(email, password);
    sessionStorage.setItem(REFRESH_KEY, res.refresh_token);
    set({ accessToken: res.access_token, user: res.user, isLoading: false });
  },

  register: async (email, password, name) => {
    const res = await registerApi(email, password, name);
    sessionStorage.setItem(REFRESH_KEY, res.refresh_token);
    set({ accessToken: res.access_token, user: res.user, isLoading: false });
  },

  logout: () => {
    sessionStorage.removeItem(REFRESH_KEY);
    set({ user: null, accessToken: null, isLoading: false });
  },

  loadUser: async () => {
    const refresh = sessionStorage.getItem(REFRESH_KEY);
    let access = get().accessToken;
    if (!access && refresh) {
      access = await get().refreshAccessToken();
    }
    if (!access) {
      set({ isLoading: false });
      return;
    }
    try {
      const user = await getMe();
      set({ user, isLoading: false });
    } catch {
      set({ user: null, accessToken: null, isLoading: false });
    }
  },

  refreshAccessToken: async () => {
    const refresh = sessionStorage.getItem(REFRESH_KEY);
    if (!refresh) {
      return null;
    }
    try {
      const res = await refreshTokenApi(refresh);
      set({ accessToken: res.access_token });
      return res.access_token;
    } catch {
      get().logout();
      return null;
    }
  },
}));
