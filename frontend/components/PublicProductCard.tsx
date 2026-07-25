/**
 * PublicProductCard — one product as a buyer sees it. SERVER-rendered (no
 * "use client"): it's static content, so it ships as HTML with no JS cost —
 * the reason we chose Next.js for the Kenyan-mobile audience. Only the small
 * <OrderButton> inside is a client component.
 *
 * Sold-out items are shown (buyers still see the drop) but visually dimmed and
 * badged, so availability reads at a glance.
 */

import { coverSrc, type PublicProduct } from "@/lib/api";
import { OrderButton } from "@/components/OrderButton";

export function PublicProductCard({ product }: { product: PublicProduct }) {
  const cover = coverSrc(product.cover_url);
  const sold = !product.is_available;

  return (
    <article className="flex flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      {/* Cover — fixed aspect ratio so the image loading never shifts layout
          (Cumulative Layout Shift is a real mobile-UX killer). */}
      <div className="relative aspect-square bg-zinc-100 dark:bg-zinc-800">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element -- served from our backend/CDN, not Next-optimized
          <img
            src={cover}
            alt={product.name || "product"}
            loading="lazy"
            className={`h-full w-full object-cover ${sold ? "opacity-50 grayscale" : ""}`}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-zinc-400">
            no image
          </div>
        )}
        {sold && (
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/80 px-4 py-1.5 text-sm font-bold uppercase tracking-wide text-white">
            Sold out
          </span>
        )}
      </div>

      {/* Details */}
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="text-sm font-semibold leading-snug text-zinc-900 dark:text-zinc-100">
          {product.name || "Untitled product"}
        </h3>
        {product.description && (
          <p className="line-clamp-2 text-xs text-zinc-500 dark:text-zinc-400">
            {product.description}
          </p>
        )}

        {/* Price + CTA pinned to the bottom so cards of varying text line up. */}
        <div className="mt-auto flex flex-col gap-3 pt-2">
          <p className="text-lg font-bold text-zinc-900 dark:text-zinc-50">
            {product.price_kes != null ? `KES ${product.price_kes.toLocaleString()}` : "—"}
          </p>
          <OrderButton available={product.is_available} />
        </div>
      </div>
    </article>
  );
}
