import { api } from "./api/client";

export type Me = { id: number; name: string; email: string; role: string | null; data_scope: string; permissions: string[] };
const TOKEN_KEY = "mf_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export async function login(email: string, password: string): Promise<Me> {
  const r = await api.post("/auth/login", { email, password });
  setToken(r.data.access_token);
  return r.data.user as Me;
}
export const fetchMe = () => api.get<Me>("/auth/me").then(r => r.data);
