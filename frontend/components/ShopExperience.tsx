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
  resolveVideo,
  type ChatMessage,
  type PublicPage,
  type PublicProduct,
} from "@/lib/api";
import { OrderButton } from "@/components/OrderButton";
import { PublicProductCard } from "@/components/PublicProductCard";

/** Spot a TikTok link in free text (full OR short) so the chat can resolve it
 *  to a product instead of shipping the raw URL to the AI. Mirrors the hosts
 *  the backend accepts. */
const TIKTOK_LINK = /https?:\/\/(?:[\w-]+\.)?tiktok\.com\/[^\s]+/i;

export function ShopExperience({
  shop,
  featuredVideoId,
}: {
  shop: PublicPage;
  featuredVideoId: string | null;
}) {
  const initialFeatured =
    (featuredVideoId && shop.products.find((p) => p.tiktok_video_id === featuredVideoId)) || null;

  // Featured is STATE (not derived): a pasted TikTok link can change it after load.
  const [featured, setFeatured] = useState<PublicProduct | null>(initialFeatured);
  const avatar = coverSrc(shop.avatar_url);
  const [catalogueOpen, setCatalogueOpen] = useState(false);

  /** One place to feature a product (from a paste, in the box or the chat): set
   *  the hero AND rewrite ?v= so the URL stays shareable and survives refresh. */
  function featureProduct(p: PublicProduct) {
    setFeatured(p);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("v", p.tiktok_video_id);
      window.history.replaceState(null, "", url.toString());
    }
  }

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

        {/* Paste-a-TikTok-link → jump to that product (context TikTok won't give us) */}
        <PasteBox handle={shop.handle} onFeature={featureProduct} hasFeatured={featured !== null} />

        {/* Product-from-video hero */}
        {featured && <FeaturedHero product={featured} />}

        {/* Chat — presented as the shop itself (avatar + name), not a "bot" */}
        <ShopChat
          handle={shop.handle}
          shopName={shop.display_name}
          avatar={avatar}
          featured={featured}
          videoId={featured?.tiktok_video_id ?? featuredVideoId}
          onFeature={featureProduct}
        />

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

// ── Paste-a-TikTok-link ──────────────────────────────────────────────────────
// TikTok won't tell us which video a shopper watched, so we let the shopper
// bring it: they tap "Copy link" on the video and paste it here → we feature it.
function PasteBox({
  handle,
  onFeature,
  hasFeatured,
}: {
  handle: string;
  onFeature: (p: PublicProduct) => void;
  hasFeatured: boolean;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function go() {
    const link = url.trim();
    if (!link || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const { product } = await resolveVideo(handle, link);
      if (product) {
        onFeature(product);
        setUrl("");
      } else {
        setNote("Sijaipata hiyo video hapa 😅 — try 'Browse all products' below.");
      }
    } catch {
      setNote("Hiyo link haikufanya kazi — jaribu tena.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-5 rounded-2xl border border-dashed border-zinc-300 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      <label className="mb-1.5 block px-1 text-xs font-medium text-zinc-500">
        🔗 {hasFeatured ? "Saw a different video? Paste its TikTok link" : "Paste the TikTok video link to see that item"}
      </label>
      <div className="flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && go()}
          placeholder="vm.tiktok.com/…"
          inputMode="url"
          className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          onClick={go}
          disabled={busy || !url.trim()}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-semibold text-white hover:bg-zinc-700 disabled:opacity-40 dark:bg-white dark:text-black"
        >
          {busy ? "…" : "Go"}
        </button>
      </div>
      {note && <p className="mt-1.5 px-1 text-xs text-amber-600">{note}</p>}
    </div>
  );
}

// ── AI chat ──────────────────────────────────────────────────────────────────
function ShopChat({
  handle,
  shopName,
  avatar,
  featured,
  videoId,
  onFeature,
}: {
  handle: string;
  shopName: string;
  avatar: string | null;
  featured: PublicProduct | null;
  videoId: string | null;
  onFeature: (p: PublicProduct) => void;
}) {
  const greeting = featured
    ? `Hi 👋 You're looking at the ${featured.name} — how can I help?`
    : `Hi 👋 Karibu! Ask me anything, or tell me what you're looking for.`;

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

    // If the customer dropped a TikTok link, resolve it to a product ourselves
    // (feature it + a natural reply) instead of sending a raw URL to the AI.
    const link = text.match(TIKTOK_LINK)?.[0];
    if (link) {
      try {
        const { product } = await resolveVideo(handle, link);
        if (product) {
          onFeature(product);
          const price = product.price_kes != null ? `KES ${product.price_kes.toLocaleString()}` : "bei on request";
          const tail = product.is_available ? "Bado iko 😊 Ungependa?" : "Lakini kwa sasa imeisha 😔";
          setMessages([...next, { role: "assistant", content: `Hiyo ni ${product.name}! ${price} — ${tail}` }]);
        } else {
          setMessages([...next, { role: "assistant", content: "Sijaipata hiyo video hapa 😅 — bonyeza 'Browse all products' uone zote." }]);
        }
      } catch {
        setMessages([...next, { role: "assistant", content: "Hiyo link haikufanya kazi — jaribu tena." }]);
      } finally {
        setTyping(false);
      }
      return;
    }

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
      {/* Chat identity: the shop itself — its avatar + name, presented as a real
          person on chat (an "online" dot), never a robot/"assistant" badge. */}
      <div className="mb-2 flex items-center gap-2 border-b border-zinc-100 px-1 pb-2 dark:border-zinc-800">
        <div className="relative h-8 w-8 shrink-0 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
          {avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={avatar} alt={shopName} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm font-bold text-zinc-500">
              {shopName.charAt(0).toUpperCase()}
            </div>
          )}
          <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-white bg-emerald-500 dark:border-zinc-900" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">{shopName}</div>
          <div className="text-[11px] text-emerald-600">online now</div>
        </div>
      </div>
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
