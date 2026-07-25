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

/** Buyer-facing product card — mirrors ProductPublicOut (deliberately narrow). */
export type PublicProduct = {
  id: number;
  cover_url: string | null;
  name: string;
  description: string;
  price_kes: number | null;
  is_available: boolean;
};

/** The whole public shop page — mirrors PublicPageOut. */
export type PublicPage = {
  handle: string;
  display_name: string;
  avatar_url: string | null;
  products: PublicProduct[];
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

// ── Seller endpoints (the dashboard) ───────────────────────────────────────

/** Paste a TikTok handle → scrape recent videos into DRAFT products. */
export async function ingestProducts(handle: string, limit = 6): Promise<Product[]> {
  const res = await fetch(`${API_URL}/api/products/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ handle, limit }),
  });
  return (await throwOnError(res)).json();
}

/** Run the 🤖 vision agent on one product (fills name + description). */
export async function autofillProduct(id: number): Promise<AutofillResult> {
  const res = await fetch(`${API_URL}/api/products/${id}/autofill`, { method: "POST" });
  return (await throwOnError(res)).json();
}

/** Seller confirms a draft: set words/price/stock, optionally publish. */
export async function updateProduct(id: number, changes: ProductUpdate): Promise<Product> {
  const res = await fetch(`${API_URL}/api/products/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
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
 * Fetch a public shop by handle, for bob.link/<handle>.
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
