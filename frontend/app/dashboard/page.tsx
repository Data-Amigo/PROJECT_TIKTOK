"use client";

/**
 * Seller dashboard — the whole M1 loop in one screen.
 *
 *   paste TikTok handle ──▶ Ingest ──▶ draft cards appear
 *                                        └▶ (per card) auto-fill → price → publish
 *
 * A client component because it's all interaction: typing, buttons, live state.
 * It talks to the backend from the BROWSER through lib/api.ts (so CORS applies —
 * the thing we set up in M0 is what makes these calls work).
 */

import { useState } from "react";
import { ingestProducts, type Product } from "@/lib/api";
import { ProductCard } from "@/components/ProductCard";

export default function DashboardPage() {
  const [handle, setHandle] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ingest() {
    if (!handle.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const rows = await ingestProducts(handle.trim());
      setProducts(rows);
    } catch (e) {
      // Designed error state: a bad handle / upstream failure shows a calm
      // message, never a blank screen or a stack trace (the POC bar).
      setError((e as Error).message);
      setProducts([]);
    } finally {
      setBusy(false);
    }
  }

  // When a card saves, swap that one product in the list so counts/badges stay
  // truthful without re-fetching everything.
  function replaceProduct(updated: Product) {
    setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  }

  return (
    <div className="mx-auto min-h-screen max-w-5xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">
          BOB <span className="text-zinc-400">Dashboard</span>
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Paste your TikTok handle. BOB pulls your recent videos — you add price and stock.
        </p>
      </header>

      {/* Paste + ingest */}
      <div className="flex gap-2">
        <input
          value={handle}
          onChange={(e) => setHandle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ingest()}
          placeholder="@kinjobales_wholesale  or  tiktok.com/@…"
          className="flex-1 rounded-lg border border-zinc-300 px-4 py-2.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          onClick={ingest}
          disabled={busy || !handle.trim()}
          className="rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-black"
        >
          {busy ? "Pulling videos…" : "Pull videos"}
        </button>
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      {/* Draft cards */}
      {products.length > 0 && (
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} onChange={replaceProduct} />
          ))}
        </div>
      )}

      {/* Empty state (only before the first pull, and only when idle) */}
      {products.length === 0 && !busy && !error && (
        <div className="mt-16 text-center text-sm text-zinc-400">
          No products yet — paste a handle above to begin.
        </div>
      )}
    </div>
  );
}
