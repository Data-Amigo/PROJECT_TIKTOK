/**
 * Public SokoLink Page — sokolink/<handle>. The shopfront real customers see.
 *
 * SERVER COMPONENT: the whole page is rendered to HTML on the server and sent
 * ready-to-paint. On a mid-range Kenyan phone over patchy data this is the
 * difference between an instant page and a spinner — the core reason this
 * project is on Next.js. The server fetch also means no CORS and no exposed
 * API surface to the browser.
 *
 * Production details that matter for testing with customers:
 *   - generateMetadata → rich link previews when the seller shares the URL on
 *     TikTok / WhatsApp / Instagram (preview image + shop name drives the click)
 *   - notFound() for an unknown handle → a real 404 page (not a broken shop)
 *   - live stock (no-store fetch) → "Available/SOLD" is never stale
 *   - friendly empty state for a shop with nothing published yet
 */

import { cache } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { coverSrc, fetchPublicPage, SHOP_NOT_FOUND } from "@/lib/api";
import { PublicProductCard } from "@/components/PublicProductCard";

// sokolink/<handle> — Next 16 hands params as a Promise.
type Params = Promise<{ handle: string }>;

// React cache() dedupes within one request: generateMetadata and the page both
// call loadShop(handle), but the backend is hit ONCE. (no-store disables Next's
// own fetch dedup, so we add this ourselves.)
const loadShop = cache((handle: string) => fetchPublicPage(handle));


export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { handle } = await params;
  let shop;
  try {
    shop = await loadShop(handle);
  } catch {
    return { title: "SokoLink" }; // backend hiccup: don't block, just a plain title
  }
  if (shop === SHOP_NOT_FOUND) return { title: "Shop not found · SokoLink" };

  // Preview image: the first product cover, else the seller's avatar.
  const previewImage =
    coverSrc(shop.products.find((p) => p.cover_url)?.cover_url ?? null) ??
    coverSrc(shop.avatar_url);

  const title = `${shop.display_name} · SokoLink`;
  const description = `Shop ${shop.display_name}'s latest drops. Pay with M-Pesa.`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      images: previewImage ? [{ url: previewImage }] : [],
    },
    twitter: {
      card: previewImage ? "summary_large_image" : "summary",
      title,
      description,
      images: previewImage ? [previewImage] : [],
    },
  };
}


export default async function BobPage({ params }: { params: Params }) {
  const { handle } = await params;
  const shop = await loadShop(handle);          // may throw → error.tsx boundary
  if (shop === SHOP_NOT_FOUND) notFound();      // → not-found.tsx (real 404)

  const avatar = coverSrc(shop.avatar_url);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <main className="mx-auto max-w-5xl px-4 py-8 sm:py-12">
        {/* Shop header — the trust signal: who am I buying from? */}
        <header className="mb-8 flex items-center gap-4">
          <div className="h-16 w-16 shrink-0 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
            {avatar ? (
              // eslint-disable-next-line @next/next/no-img-element -- backend/CDN host
              <img src={avatar} alt={shop.display_name} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-xl font-bold text-zinc-400">
                {shop.display_name.charAt(0).toUpperCase()}
              </div>
            )}
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50 sm:text-2xl">
              {shop.display_name}
            </h1>
            <p className="text-sm text-zinc-500">@{shop.handle} · Pay with M-Pesa</p>
          </div>
        </header>

        {/* Product grid — 2-up on phones (most buyers), more on wider screens. */}
        {shop.products.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-4">
            {shop.products.map((p) => (
              <PublicProductCard key={p.id} product={p} />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center dark:border-zinc-700">
            <p className="text-sm text-zinc-500">
              {shop.display_name} hasn&apos;t posted any drops yet — check back soon.
            </p>
          </div>
        )}

        {/* Trust footer */}
        <footer className="mt-12 border-t border-zinc-200 pt-6 text-center dark:border-zinc-800">
          <p className="text-xs text-zinc-400">
            Powered by <span className="font-semibold text-zinc-600 dark:text-zinc-300">SokoLink</span>{" "}
            · Where your audience becomes your customers
          </p>
        </footer>
      </main>
    </div>
  );
}
