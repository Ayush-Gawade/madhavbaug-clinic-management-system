/** Authentication provider: current user, login and logout. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { AuthContext, type AuthContextValue, type AuthStatus } from "./auth-context";
import { apiFetch } from "./api";
import { tokenStore } from "./tokenStore";
import type { StaffUser, TokenPair } from "./types";

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<StaffUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    let active = true;
    const bootstrap = async (): Promise<void> => {
      if (!tokenStore.getAccess()) {
        if (active) setStatus("anonymous");
        return;
      }
      try {
        const me = await apiFetch<StaffUser>("/auth/me");
        if (active) {
          setUser(me);
          setStatus("authenticated");
        }
      } catch {
        tokenStore.clear();
        if (active) setStatus("anonymous");
      }
    };
    void bootstrap();
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const pair = await apiFetch<TokenPair>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    tokenStore.set(pair.access_token, pair.refresh_token);
    const me = await apiFetch<StaffUser>("/auth/me");
    setUser(me);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    const refresh = tokenStore.getRefresh();
    if (refresh) {
      try {
        await apiFetch<void>("/auth/logout", {
          method: "POST",
          body: { refresh_token: refresh },
          auth: false,
        });
      } catch {
        // Ignore revocation errors; local state is cleared regardless.
      }
    }
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, logout }),
    [user, status, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
