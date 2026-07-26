"use client";

/**
 * ShopExperience — the buyer's conversational storefront (M5).
 *
 *   Video → AI Sales Agent → Catalogue → Checkout
 *
 * Layout (mobile-first):
 *   • shop header
 *   • product-from-video hero (when the link carries ?v=<video_id>)
 *   • 🤖 AI chat — greets with the featured product, answers from the catalogue
 *   • "Browse all products" → catalogue as a bottom-sheet
 *
 * The data is fetched server-side (fast, SEO); this client component adds the
 * interactivity. "Buy Now" is honest coming-soon until M-Pesa (M4) is wired.
 */

import { useEffect, useRef, useState } from "react";
import {
  chatWithShop,
  coverSrc,
  type ChatMessage,
  type PublicPage,
  type PublicProduct,
} from "@/lib/api";
import { OrderButton } from "@/components/OrderButton";
import { PublicProductCard } from "@/components/PublicProductCard";

export function ShopExperience({
  shop,
  featuredVideoId,
}: {
  shop: PublicPage;
  featuredVideoId: string | null;
}) {
  const featured =
    (featuredVideoId && shop.products.find((p) => p.tiktok_video_id === featuredVideoId)) ||
    null;

  const avatar = coverSrc(shop.avatar_url);
  const [catalogueOpen, setCatalogueOpen] = useState(false);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <main className="mx-auto max-w-md px-4 py-6">
        {/* Shop header */}
        <header className="mb-5 flex items-center gap-3">
          <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
            {avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={avatar} alt={shop.display_name} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center font-bold text-zinc-400">
                {shop.display_name.charAt(0).toUpperCase()}
              </div>
            )}
          </div>
          <div>
            <h1 className="font-bold leading-tight text-zinc-900 dark:text-zinc-50">{shop.display_name}</h1>
            <p className="text-xs text-zinc-500">@{shop.handle} · Pay with M-Pesa</p>
          </div>
        </header>

        {/* Product-from-video hero */}
        {featured && <FeaturedHero product={featured} />}

        {/* AI chat */}
        <ShopChat handle={shop.handle} featured={featured} videoId={featuredVideoId} />

        {/* Browse all */}
        <button
          onClick={() => setCatalogueOpen(true)}
          className="mt-4 w-full rounded-xl border border-zinc-300 bg-white py-3 text-sm font-semibold hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          🛍️ Browse all products ({shop.products.length})
        </button>

        <footer className="mt-10 border-t border-zinc-200 pt-6 text-center dark:border-zinc-800">
          <p className="text-xs text-zinc-400">
            Powered by <span className="font-semibold text-zinc-600 dark:text-zinc-300">SokoLink</span>{" "}
            · Where your audience becomes your customers
          </p>
        </footer>
      </main>

      {catalogueOpen && (
        <CatalogueSheet products={shop.products} onClose={() => setCatalogueOpen(false)} />
      )}
    </div>
  );
}

// ── Featured product (from the video) ────────────────────────────────────────
function FeaturedHero({ product }: { product: PublicProduct }) {
  const cover = coverSrc(product.cover_url);
  return (
    <div className="mb-5 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="relative aspect-square bg-zinc-100 dark:bg-zinc-800">
        {cover && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={cover}
            alt={product.name}
            className={`h-full w-full object-cover ${product.is_available ? "" : "opacity-50 grayscale"}`}
          />
        )}
        <span className="absolute left-3 top-3 rounded-full bg-black/80 px-3 py-1 text-xs font-medium text-white">
          🎬 From the video
        </span>
        {!product.is_available && (
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/80 px-4 py-1.5 text-sm font-bold uppercase text-white">
            Sold out
          </span>
        )}
      </div>
      <div className="p-4">
        <h2 className="text-base font-semibold">{product.name || "Untitled product"}</h2>
        {product.description && (
          <p className="mt-1 line-clamp-2 text-xs text-zinc-500">{product.description}</p>
        )}
        <p className="mt-2 text-xl font-bold">
          {product.price_kes != null ? `KES ${product.price_kes.toLocaleString()}` : "—"}
        </p>
        <div className="mt-3">
          <OrderButton available={product.is_available} />
        </div>
      </div>
    </div>
  );
}

// ── AI chat ──────────────────────────────────────────────────────────────────
function ShopChat({
  handle,
  featured,
  videoId,
}: {
  handle: string;
  featured: PublicProduct | null;
  videoId: string | null;
}) {
  const greeting = featured
    ? `Hi 👋 You're looking at the ${featured.name} — how can I help?`
    : `Hi 👋 Welcome! Ask me anything, or tell me what you're looking for.`;

  // messages[0] is the static greeting (shown, not sent). The API gets the rest.
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "assistant", content: greeting }]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  async function send() {
    const text = input.trim();
    if (!text || typing) return;
    setInput("");
    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setTyping(true);
    try {
      const reply = await chatWithShop(handle, next.slice(1), videoId); // drop static greeting
      setMessages([...next, { role: "assistant", content: reply }]);
    } catch {
      setMessages([...next, { role: "assistant", content: "Sorry, I had a hiccup — please try again." }]);
    } finally {
      setTyping(false);
    }
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-1 px-1 text-xs font-medium text-zinc-400">🤖 Shop assistant</div>
      <div className="flex max-h-80 flex-col gap-2 overflow-y-auto px-1 py-2">
        {messages.map((m, i) => (
          <Bubble key={i} role={m.role} text={m.content} />
        ))}
        {typing && <Bubble role="assistant" text="…" />}
        <div ref={endRef} />
      </div>
      <div className="mt-2 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about sizes, colours, price…"
          className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          onClick={send}
          disabled={typing || !input.trim()}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}

function Bubble({ role, text }: { role: "user" | "assistant"; text: string }) {
  const mine = role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
          mine
            ? "bg-black text-white dark:bg-white dark:text-black"
            : "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100"
        }`}
      >
        {text}
      </div>
    </div>
  );
}

// ── Catalogue bottom-sheet ───────────────────────────────────────────────────
function CatalogueSheet({
  products,
  onClose,
}: {
  products: PublicProduct[];
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const filtered = q.trim()
    ? products.filter((p) => p.name.toLowerCase().includes(q.trim().toLowerCase()))
    : products;

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/40" onClick={onClose}>
      <div
        className="max-h-[85vh] overflow-y-auto rounded-t-2xl bg-zinc-50 p-4 dark:bg-black"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-bold">Catalogue</h3>
          <button onClick={onClose} className="text-2xl leading-none text-zinc-400 hover:text-zinc-700">
            ×
          </button>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search products…"
          className="mb-4 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
        />
        {filtered.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {filtered.map((p) => (
              <PublicProductCard key={p.id} product={p} />
            ))}
          </div>
        ) : (
          <p className="py-10 text-center text-sm text-zinc-400">No products match “{q}”.</p>
        )}
      </div>
    </div>
  );
}
