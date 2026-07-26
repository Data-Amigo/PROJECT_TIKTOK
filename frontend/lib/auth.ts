/**
 * Auth client — signup / login / who-am-I.
 *
 * Token storage + authHeader live in lib/api.ts (so api.ts can attach auth
 * without importing this file — avoids a circular import). This module owns
 * the account-identity calls and re-exports the logout helper.
 */

import { API_URL, clearToken, getToken, setToken, throwOnError } from "@/lib/api";

export type Account = {
  id: number;
  name: string;
  email: string;
  phone: string;
  created_at: string;
};

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

/** The logged-in account, or null. Clears a dead token so the app falls back
 *  cleanly to logged-out. */
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
