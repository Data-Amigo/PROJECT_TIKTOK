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
import { ShopExperience } from "@/components/ShopExperience";

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


export default async function ShopPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<{ v?: string }>;
}) {
  const { handle } = await params;
  const { v } = await searchParams; // ?v=<video_id> → feature the product from that video
  const shop = await loadShop(handle);          // may throw → error.tsx boundary
  if (shop === SHOP_NOT_FOUND) notFound();      // → not-found.tsx (real 404)

  // Server-fetched data (fast, SEO) handed to the interactive client experience.
  return <ShopExperience shop={shop} featuredVideoId={v ?? null} />;
}
