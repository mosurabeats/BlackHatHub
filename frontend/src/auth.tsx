import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, post, setCsrf } from "./api";

export type AuthStatus = {
  setup_required: boolean;
  authenticated: boolean;
  user: { username: string; totp_enabled: boolean } | null;
  csrf_token: string | null;
  vault: { unlocked: boolean; idle_timeout_minutes: number; locks_at?: string };
  vault_initial_pin: boolean | null;
};

type Ctx = {
  status: AuthStatus | null;
  refresh: () => Promise<void>;
  lockVault: () => Promise<void>;
  logout: () => Promise<void>;
  vaultVersion: number;
};

const AuthCtx = createContext<Ctx>({
  status: null,
  refresh: async () => {},
  lockVault: async () => {},
  logout: async () => {},
  vaultVersion: 0,
});
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [vaultVersion, setVaultVersion] = useState(0);
  const lastUnlocked = useRef<boolean | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api<AuthStatus>("/auth/status", { background: true });
      setCsrf(s.csrf_token);
      if (lastUnlocked.current !== null && lastUnlocked.current !== s.vault.unlocked) setVaultVersion((v) => v + 1);
      lastUnlocked.current = s.vault.unlocked;
      setStatus(s);
    } catch {
      /* server unreachable; keep last state */
    }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauth = () => refresh();
    window.addEventListener("exechub:unauthorized", onUnauth);
    const t = setInterval(refresh, 30000); // detects vault idle-lock and session expiry
    return () => {
      window.removeEventListener("exechub:unauthorized", onUnauth);
      clearInterval(t);
    };
  }, [refresh]);

  const lockVault = async () => {
    await post("/vault/lock");
    await refresh();
  };
  const logout = async () => {
    await post("/auth/logout");
    setCsrf(null);
    await refresh();
  };

  return <AuthCtx.Provider value={{ status, refresh, lockVault, logout, vaultVersion }}>{children}</AuthCtx.Provider>;
}
