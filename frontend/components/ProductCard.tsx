"use client";

/**
 * ProductCard — one scraped video the seller turns into a listing.
 *
 * The seller's journey through this card mirrors the backend rules exactly:
 *   1. Auto-fill  → the 🤖 vision agent suggests a name + description (words only)
 *   2. Edit       → the seller corrects the words
 *   3. Price + stock → the seller sets the MONEY (the agent never could)
 *   4. Publish    → goes live (the button is disabled until there's a price —
 *                   the same rule the API and the DB enforce, surfaced early
 *                   so the seller never hits a confusing server error)
 *
 * A "client component" (note "use client"): it holds editable state and calls
 * the backend from the browser — which is exactly why CORS exists and why we
 * configured it back in M0.
 */

import { useState } from "react";
import {
  autofillProduct,
  coverSrc,
  updateProduct,
  type Product,
} from "@/lib/api";

export function ProductCard({
  product,
  onChange,
}: {
  product: Product;
  onChange: (updated: Product) => void; // lift changes up so the list stays in sync
}) {
  // Local editable copies. We edit these freely; only Save/Publish send them
  // to the backend. (Price/stock are strings while typing, parsed on submit —
  // an empty input is "no value", not 0.)
  const [name, setName] = useState(product.name);
  const [description, setDescription] = useState(product.description);
  const [price, setPrice] = useState(product.price_kes?.toString() ?? "");
  const [stock, setStock] = useState(product.stock.toString());

  const [busy, setBusy] = useState<null | "autofill" | "save" | "publish">(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null); // agent's language note
  const [priceFromImage, setPriceFromImage] = useState(false); // price was pre-filled from the cover
  const [notProduct, setNotProduct] = useState<string | null>(null); // agent thinks this isn't a product

  const cover = coverSrc(product.cover_url);
  const hasPrice = price.trim() !== "" && Number(price) > 0;

  async function runAutofill() {
    setBusy("autofill");
    setError(null);
    setNote(null);
    setPriceFromImage(false);
    setNotProduct(null);
    try {
      const result = await autofillProduct(product.id);
      setName(result.product.name);
      setDescription(result.product.description);
      onChange(result.product);
      // Pre-fill the price ONLY if the agent read one off the image AND the
      // seller hasn't typed their own yet — never overwrite the human.
      if (result.suggested_price_kes != null && price.trim() === "") {
        setPrice(String(result.suggested_price_kes));
        setPriceFromImage(true);
      }
      if (!result.is_product) {
        setNotProduct(result.not_product_reason || "This may not be a product.");
      }
      if (result.language_note) setNote(result.language_note);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function save(publish: boolean) {
    setBusy(publish ? "publish" : "save");
    setError(null);
    try {
      const updated = await updateProduct(product.id, {
        name,
        description,
        // Only send price/stock when they parse to a number — an empty box
        // means "leave unset", not "set to 0".
        price_kes: price.trim() === "" ? undefined : Number(price),
        stock: stock.trim() === "" ? undefined : Number(stock),
        publish,
      });
      onChange(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      {/* Cover + status */}
      <div className="relative aspect-square overflow-hidden rounded-lg bg-zinc-100 dark:bg-zinc-800">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element -- external host, not Next-optimized
          <img src={cover} alt={name || "product cover"} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-zinc-400">
            no cover
          </div>
        )}
        <StatusBadge product={product} />
      </div>

      {/* Auto-fill is a MANUAL FALLBACK only — products are drafted
          automatically on connect/refresh. This shows only when a product came
          back un-drafted (e.g. the AI daily limit was hit). */}
      {!product.name && (
        <button
          onClick={runAutofill}
          disabled={busy !== null}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          {busy === "autofill" ? "Reading the image…" : "✨ Auto-fill from image"}
        </button>
      )}
      {note && (
        <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Translated: {note}
        </p>
      )}
      {notProduct && (
        <p className="rounded bg-orange-50 px-2 py-1 text-xs text-orange-800 dark:bg-orange-950 dark:text-orange-200">
          ⚠️ This may not be a product ({notProduct}). Review before publishing.
        </p>
      )}

      {/* Words (agent proposes, seller edits) */}
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Product name"
        className="rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description"
        rows={2}
        className="resize-none rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
      />

      {/* Money (only the seller, ever) */}
      <div className="flex gap-2">
        <label className="flex-1 text-xs text-zinc-500">
          Price (KES)
          <input
            type="number"
            min={1}
            value={price}
            onChange={(e) => {
              setPrice(e.target.value);
              setPriceFromImage(false); // seller took over — it's their number now
            }}
            placeholder="800"
            className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm dark:bg-zinc-950 ${
              priceFromImage
                ? "border-emerald-400 dark:border-emerald-600"
                : "border-zinc-300 dark:border-zinc-700"
            }`}
          />
          {priceFromImage && (
            <span className="mt-0.5 block text-[11px] text-emerald-600 dark:text-emerald-400">
              read from image — confirm it
            </span>
          )}
        </label>
        <label className="flex-1 text-xs text-zinc-500">
          Stock
          <input
            type="number"
            min={0}
            value={stock}
            onChange={(e) => setStock(e.target.value)}
            className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </label>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={() => save(false)}
          disabled={busy !== null}
          className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          {busy === "save" ? "Saving…" : "Save draft"}
        </button>
        <button
          onClick={() => save(true)}
          // Disabled without a price: the exact rule the API + DB enforce,
          // shown BEFORE the seller can trigger the error.
          disabled={busy !== null || !hasPrice}
          title={hasPrice ? "" : "Set a price first"}
          className="flex-1 rounded-lg bg-black px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-black"
        >
          {busy === "publish" ? "Publishing…" : product.status === "published" ? "Update" : "Publish"}
        </button>
      </div>
    </div>
  );
}

/** Small status pill overlaid on the cover. */
function StatusBadge({ product }: { product: Product }) {
  let label = "Draft";
  let color = "bg-zinc-900/80 text-white";
  if (product.status === "published") {
    if (product.is_available) {
      label = "Available";
      color = "bg-green-600 text-white";
    } else {
      label = "Sold out";
      color = "bg-red-600 text-white";
    }
  }
  return (
    <span className={`absolute right-2 top-2 rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}
