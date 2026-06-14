import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchMe, getToken, clearToken, type Me } from "../auth";

type Ctx = { me: Me | null; loading: boolean; can: (c: string) => boolean; logout: () => void; setMe: (m: Me | null) => void };
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    fetchMe().then(setMe).catch(() => clearToken()).finally(() => setLoading(false));
  }, []);
  const can = (c: string) => !!me && (me.permissions.includes("*") || me.permissions.includes(c));
  const logout = () => { clearToken(); setMe(null); location.href = "/login"; };
  return <AuthCtx.Provider value={{ me, loading, can, logout, setMe }}>{children}</AuthCtx.Provider>;
}
