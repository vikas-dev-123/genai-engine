import { useEffect } from "react";

import { useAuthStore } from "../store/authStore";

export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const isLoading = useAuthStore((s) => s.isLoading);
  const loadUser = useAuthStore((s) => s.loadUser);
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    void loadUser();
  }, [loadUser]);

  return {
    user,
    isLoading,
    isAuthenticated: Boolean(user),
    logout,
  };
}
