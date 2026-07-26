/**
 * API client — the frontend's ONLY door to the backend.
 *
 *   page/component ──> lib/api.ts ──> FastAPI (NEXT_PUBLIC_API_URL)
 *
 * Rule (mirrors the backend's config.py rule): no component ever calls
 * `fetch` against the backend directly. Every call goes through here, so
 * base-URL handling, types, and error behaviour live in exactly one place.
 * These TypeScript types mirror backend/app/schemas/product.py — keep in sync.
 */

// Read once at module level. In the browser this string was inlined at
// build time (NEXT_PUBLIC_); on the server it's a normal env read.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

// ── Token storage (the auth layer both api.ts and auth.ts build on) ─────────
// Kept here (not auth.ts) so api.ts can attach auth headers without importing
// auth.ts — that would be a circular import. Guarded for SSR (no window).
const TOKEN_KEY = "sokolink_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
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

// ── Types (mirror of the pydantic *Out schemas) ────────────────────────────
export type ProductStatus = "draft" | "published";

/** Full seller-facing product — mirrors ProductOut. */
export type Product = {
  id: number;
  tiktok_video_id: string;
  video_url: string;
  cover_url: string | null;
  name: string;
  description: string;
  price_kes: number | null;
  stock: number;
  status: ProductStatus;
  is_available: boolean;
  created_at: string;
};

export type AutofillResult = {
  product: Product;
  is_product: boolean;
  not_product_reason: string;
  suggested_price_kes: number | null; // pre-fills the price box; seller confirms
  suggested_tags: string[];
  language_note: string;
};

/** Batch auto-draft result. ai_paused = the AI cap stopped the run partway. */
export type AutodraftResult = { products: Product[]; ai_paused: boolean };

/** Buyer-facing product card — mirrors ProductPublicOut (deliberately narrow). */
export type PublicProduct = {
  id: number;
  tiktok_video_id: string;
  cover_url: string | null;
  name: string;
  description: string;
  price_kes: number | null;
  is_available: boolean;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

/** The whole public shop page — mirrors PublicPageOut. */
export type PublicPage = {
  handle: string;
  display_name: string;
  avatar_url: string | null;
  products: PublicProduct[];
};

/** The seller's own storefront — mirrors StorefrontOut. */
export type Storefront = {
  handle: string;
  display_name: string;
  tiktok_username: string | null;
  bio: string;
  avatar_url: string | null;
  follower_count: number;
  phone: string | null;
};

/** Fields a PATCH may change — mirrors ProductUpdateIn (all optional). */
export type ProductUpdate = {
  name?: string;
  description?: string;
  price_kes?: number;
  stock?: number;
  publish?: boolean;
};

// ── Health (server component, unchanged from M0) ───────────────────────────
export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  env: string;
  checks: Record<string, string>;
};

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    const res = await fetch(`${API_URL}/health`);
    if (!res.ok) return null;
    return (await res.json()) as HealthResponse;
  } catch {
    return null;
  }
}

// ── Shared error handling ──────────────────────────────────────────────────
/**
 * FastAPI returns errors as `{ detail: "..." }` (a string) or, for validation
 * failures, `{ detail: [ {msg, loc, ...} ] }` (an array). This normalizes both
 * into one human message the UI can show — so a component never has to know
 * which shape it got.
 */
export async function throwOnError(res: Response): Promise<Response> {
  if (res.ok) return res;
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* non-JSON error body — keep the status-code message */
  }
  throw new Error(message);
}

// ── Cover images ───────────────────────────────────────────────────────────
/** Turn a stored cover_url ("covers/123.jpg") into a full URL the <img> can
 *  load. Returns null when there's no cover, so the caller shows a placeholder. */
export function coverSrc(cover_url: string | null): string | null {
  return cover_url ? `${API_URL}/media/${cover_url}` : null;
}

// ── Seller endpoints (all require login → authHeader) ──────────────────────

/** Connect a TikTok username → build the storefront + pull recent videos. */
export async function connectTikTok(username: string): Promise<Storefront> {
  const res = await fetch(`${API_URL}/api/account/connect-tiktok`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ username }),
  });
  return (await throwOnError(res)).json();
}

/** The account's storefront, or null if TikTok isn't connected yet. */
export async function fetchStorefront(): Promise<Storefront | null> {
  const res = await fetch(`${API_URL}/api/account/storefront`, { headers: authHeader() });
  if (!res.ok) return null;
  return res.json(); // backend returns null (not 404) when not connected
}

/** The seller's own products (drafts + published). */
export async function fetchMyProducts(): Promise<Product[]> {
  const res = await fetch(`${API_URL}/api/products/mine`, { headers: authHeader() });
  return (await throwOnError(res)).json();
}

/** Re-pull the connected TikTok's latest videos into draft products. */
export async function refreshProducts(): Promise<Product[]> {
  const res = await fetch(`${API_URL}/api/products/refresh`, {
    method: "POST",
    headers: authHeader(),
  });
  return (await throwOnError(res)).json();
}

/** Auto-draft all un-drafted products (name/description + a readable price).
 *  The seller only reviews + publishes — no per-product clicking. */
export async function autodraftProducts(): Promise<AutodraftResult> {
  const res = await fetch(`${API_URL}/api/products/autodraft`, {
    method: "POST",
    headers: authHeader(),
  });
  return (await throwOnError(res)).json();
}

/** Run the 🤖 vision agent on ONE product (manual fallback when AI is paused). */
export async function autofillProduct(id: number): Promise<AutofillResult> {
  const res = await fetch(`${API_URL}/api/products/${id}/autofill`, {
    method: "POST",
    headers: authHeader(),
  });
  return (await throwOnError(res)).json();
}

/** Seller confirms a draft: set words/price/stock, optionally publish. */
export async function updateProduct(id: number, changes: ProductUpdate): Promise<Product> {
  const res = await fetch(`${API_URL}/api/products/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(changes),
  });
  return (await throwOnError(res)).json();
}

// ── Buyer endpoint (the public page — server-rendered) ─────────────────────

/** Sentinel the public page uses to tell "no such shop" apart from "backend
 *  is down". Returning it (instead of null-for-both) lets the page show a real
 *  404 for a bad handle but a "try again" error when our own service is down —
 *  two very different messages a real customer must not see confused. */
export const SHOP_NOT_FOUND = Symbol("shop-not-found");

/**
 * Fetch a public shop by handle, for sokolink/<handle>.
 *
 * `cache: "no-store"` — availability changes with every sale, so the page must
 * read live stock, never a stale snapshot. A customer seeing "Available" on a
 * sold-out item is the one bug this page cannot have.
 *
 * Returns the page, or SHOP_NOT_FOUND for a 404. Any OTHER failure THROWS, so
 * the route's error boundary shows "something went wrong" rather than lying
 * that the shop doesn't exist.
 */
export async function fetchPublicPage(handle: string): Promise<PublicPage | typeof SHOP_NOT_FOUND> {
  const res = await fetch(`${API_URL}/api/pages/${encodeURIComponent(handle)}`, {
    cache: "no-store",
  });
  if (res.status === 404) return SHOP_NOT_FOUND;
  if (!res.ok) throw new Error(`Shop fetch failed (${res.status})`);
  return res.json();
}

/** What a pasted TikTok link resolved to. `product` is null when the link
 *  didn't match one of this shop's products (see ResolveVideoOut). */
export type ResolvedVideo = { video_id: string | null; product: PublicProduct | null };

/** Resolve a TikTok video link a customer pasted → the product it features.
 *  Accepts full OR short links (the backend follows short-link redirects). */
export async function resolveVideo(handle: string, url: string): Promise<ResolvedVideo> {
  const res = await fetch(`${API_URL}/api/pages/${encodeURIComponent(handle)}/resolve-video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  return (await throwOnError(res)).json();
}

/** Ask the shop's 🤖 sales agent. `messages` is the conversation (starts with a
 *  user turn); `videoId` is the video the buyer arrived from (?v=), if any. */
export async function chatWithShop(
  handle: string,
  messages: ChatMessage[],
  videoId: string | null,
): Promise<string> {
  const res = await fetch(`${API_URL}/api/pages/${encodeURIComponent(handle)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, video_id: videoId }),
  });
  const data = await (await throwOnError(res)).json();
  return data.reply as string;
}
