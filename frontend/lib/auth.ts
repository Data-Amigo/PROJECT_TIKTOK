/**
 * Auth client — signup / login / who-am-I, plus token storage.
 *
 * The JWT from the backend is kept in localStorage and sent as
 * `Authorization: Bearer <token>` on protected calls. (localStorage is the
 * pragmatic choice for a pilot SPA; a stricter httpOnly-cookie setup is a noted
 * hardening step for later — see the workplan.) All token handling lives HERE
 * so no component touches localStorage directly.
 */

import { API_URL, throwOnError } from "@/lib/api";

const TOKEN_KEY = "sokolink_token";

export type Account = {
  id: number;
  name: string;
  email: string;
  phone: string;
  created_at: string;
};

// ── Token storage (guarded for SSR — window is undefined on the server) ─────
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}

/** Authorization header for protected requests, or {} when logged out. */
export function authHeader(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

// ── Calls ───────────────────────────────────────────────────────────────────
export async function signup(input: {
  name: string;
  email: string;
  phone: string;
  password: string;
}): Promise<void> {
  const res = await fetch(`${API_URL}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const data = await (await throwOnError(res)).json();
  setToken(data.access_token); // signup logs you straight in
}

export async function login(email: string, password: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await (await throwOnError(res)).json();
  setToken(data.access_token);
}

/** The logged-in account, or null if not authenticated. Clears a dead token
 *  (expired/invalid) so the app cleanly falls back to logged-out. */
export async function fetchMe(): Promise<Account | null> {
  const token = getToken();
  if (!token) return null;
  const res = await fetch(`${API_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    if (res.status === 401) clearToken();
    return null;
  }
  return res.json();
}

export function logout(): void {
  clearToken();
}
