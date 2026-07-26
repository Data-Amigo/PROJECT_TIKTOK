"use client";

/**
 * Seller dashboard — the account-first shop manager.
 *
 *   log in ─▶ (no TikTok) Connect ─▶ (connected) storefront + AUTO-DRAFTED products
 *
 * The seller does no per-product "auto-fill" clicking: on connect (and when new
 * videos arrive) every un-drafted product is drafted automatically by the AI
 * (name, description, and a price it can read). The seller only reviews, sets
 * any missing prices, and publishes.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  autodraftProducts,
  connectTikTok,
  coverSrc,
  fetchMyProducts,
  fetchStorefront,
  refreshProducts,
  type Product,
  type Storefront,
} from "@/lib/api";
import { fetchMe, logout, type Account } from "@/lib/auth";
import { ProductCard } from "@/components/ProductCard";

type Phase = "loading" | "connect" | "shop";

export default function DashboardPage() {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [storefront, setStorefront] = useState<Storefront | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [phase, setPhase] = useState<Phase>("loading");
  const [drafting, setDrafting] = useState(false);
  const [aiPaused, setAiPaused] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Load the seller's products, then auto-draft any that aren't drafted yet.
  const loadAndDraft = useCallback(async () => {
    const initial = await fetchMyProducts();
    setProducts(initial);
    if (initial.some((p) => !p.name.trim())) {
      setDrafting(true);
      try {
        const res = await autodraftProducts();
        setProducts(res.products);
        setAiPaused(res.ai_paused);
      } finally {
        setDrafting(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchMe().then(async (acct) => {
      if (!acct) {
        router.replace("/login");
        return;
      }
      setAccount(acct);
      const shop = await fetchStorefront();
      if (shop) {
        setStorefront(shop);
        setPhase("shop");
        await loadAndDraft();
      } else {
        setPhase("connect");
      }
    });
  }, [router, loadAndDraft]);

  const onConnected = useCallback(
    async (shop: Storefront) => {
      setStorefront(shop);
      setPhase("shop");
      await loadAndDraft();
    },
    [loadAndDraft],
  );

  async function onRefresh() {
    setRefreshing(true);
    setAiPaused(false);
    try {
      setProducts(await refreshProducts()); // pull new videos (un-drafted)
      await loadAndDraft(); // draft whatever's new
    } finally {
      setRefreshing(false);
    }
  }

  function signOut() {
    logout();
    router.replace("/login");
  }

  const replaceProduct = (updated: Product) =>
    setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));

  if (phase === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 text-sm text-zinc-400 dark:bg-black">
        Loading your shop…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <nav className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="text-lg font-bold tracking-tight">
            Soko<span className="text-zinc-400">Link</span>
          </span>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-zinc-500">{account?.name}</span>
            <button onClick={signOut} className="text-zinc-400 underline hover:text-zinc-700 dark:hover:text-zinc-200">
              Log out
            </button>
          </div>
        </div>
      </nav>

      {phase === "connect" ? (
        <ConnectScreen onConnected={onConnected} />
      ) : (
        storefront && (
          <ShopView
            storefront={storefront}
            products={products}
            drafting={drafting}
            aiPaused={aiPaused}
            refreshing={refreshing}
            onRefresh={onRefresh}
            onReplaceProduct={replaceProduct}
          />
        )
      )}
    </div>
  );
}

// ── Connect screen ────────────────────────────────────────────────────────────
function ConnectScreen({ onConnected }: { onConnected: (s: Storefront) => void }) {
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    if (!username.trim()) return;
    setBusy(true);
    setError(null);
    try {
      onConnected(await connectTikTok(username.trim()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-6 py-20 text-center">
      <div className="text-5xl">🔗</div>
      <h1 className="mt-4 text-2xl font-bold tracking-tight">Connect your TikTok</h1>
      <p className="mt-2 text-sm text-zinc-500">
        We&apos;ll pull your recent videos and draft them into products automatically —
        you just review, price, and publish.
      </p>
      <div className="mt-8 flex gap-2">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && connect()}
          placeholder="@your_tiktok"
          className="flex-1 rounded-lg border border-zinc-300 px-4 py-2.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          onClick={connect}
          disabled={busy || !username.trim()}
          className="rounded-lg bg-black px-5 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-black"
        >
          {busy ? "Connecting…" : "Connect"}
        </button>
      </div>
      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}
    </div>
  );
}

// ── Shop view ────────────────────────────────────────────────────────────────
function ShopView({
  storefront,
  products,
  drafting,
  aiPaused,
  refreshing,
  onRefresh,
  onReplaceProduct,
}: {
  storefront: Storefront;
  products: Product[];
  drafting: boolean;
  aiPaused: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  onReplaceProduct: (p: Product) => void;
}) {
  const avatar = coverSrc(storefront.avatar_url);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      {/* Storefront profile */}
      <div className="flex flex-col items-start gap-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 sm:flex-row sm:items-center">
        <div className="h-16 w-16 shrink-0 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          {avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={avatar} alt={storefront.display_name} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-xl font-bold text-zinc-400">
              {storefront.display_name.charAt(0).toUpperCase()}
            </div>
          )}
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight">{storefront.display_name}</h1>
          <p className="text-sm text-zinc-500">
            @{storefront.tiktok_username} · {formatCount(storefront.follower_count)} followers
          </p>
        </div>
        <div className="flex gap-2">
          <a
            href={`/${storefront.handle}`}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            View my shop ↗
          </a>
          <button
            onClick={onRefresh}
            disabled={refreshing || drafting}
            className="rounded-lg bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-black"
          >
            {refreshing ? "Refreshing…" : "↻ Refresh videos"}
          </button>
        </div>
      </div>

      {/* AI status banners */}
      {drafting && (
        <p className="mt-6 flex items-center gap-2 rounded-lg bg-zinc-100 px-4 py-3 text-sm text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          <span className="animate-pulse">✨</span> AI is drafting your products — names, descriptions, and prices it can read…
        </p>
      )}
      {aiPaused && !drafting && (
        <p className="mt-6 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
          AI drafting paused — today&apos;s image-reading limit was reached. Un-drafted items can be
          filled in manually, or enable Gemini billing to lift the limit.
        </p>
      )}

      {/* Products */}
      <div className="mt-8 mb-4 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Your products</h2>
        <span className="text-sm text-zinc-400">{products.length} item{products.length === 1 ? "" : "s"}</span>
      </div>

      {products.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            // Key includes drafted-ness: when a product goes un-drafted → drafted
            // (auto-fill arrives), the key changes and the card remounts, so its
            // editable fields pick up the drafted name/price instead of staying
            // blank. Once drafted the key is stable, so edits don't remount it.
            <ProductCard
              key={`${p.id}-${p.name.trim() ? "d" : "u"}`}
              product={p}
              onChange={onReplaceProduct}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center text-sm text-zinc-400 dark:border-zinc-700">
          No products yet. Tap <span className="font-medium">Refresh videos</span> to pull your latest TikToks.
        </div>
      )}
    </div>
  );
}

/** 1400000 → "1.4M", 12500 → "12.5K". */
function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(n);
}
