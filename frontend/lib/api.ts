/**
 * API client — the frontend's ONLY door to the backend.
 *
 *   page/component ──> lib/api.ts ──> FastAPI (NEXT_PUBLIC_API_URL)
 *
 * Rule (mirrors the backend's config.py rule): no component ever calls
 * `fetch` against the backend directly. Every call goes through here, so
 * base-URL handling, types, and error behaviour live in exactly one place.
 * When shared/schemas/ becomes real, its types replace the hand-written
 * ones below.
 */

// Read once at module level. In the browser this string was inlined at
// build time (NEXT_PUBLIC_); on the server it's a normal env read.
// The fallback keeps a fresh clone working with zero setup.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

/** Mirror of the backend's /health response — keep in sync with app/main.py. */
export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  env: string;
  checks: Record<string, string>; // e.g. { api: "ok", db: "ok" }
};

/**
 * Fetch backend health. Returns null when the backend is unreachable —
 * the CALLER decides how to render that (designed error states, not
 * exceptions bubbling into a user's face).
 *
 * Next 16 note: fetch is UNCACHED by default here (older Next versions
 * cached aggressively — that changed; see AGENTS.md's warning). A health
 * check must always be live, so the default is exactly what we want.
 */
export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    const res = await fetch(`${API_URL}/health`);
    if (!res.ok) return null;
    return (await res.json()) as HealthResponse;
  } catch {
    // Backend down / DNS / refused — same answer for the caller: no data.
    return null;
  }
}
